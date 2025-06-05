from django.views.generic import (ListView, DetailView, CreateView,
                                  UpdateView, DeleteView)
from django.shortcuts import get_object_or_404, redirect
from .models import Post, Category, Comment
from django.utils import timezone
from django.conf import settings
from .forms import PostCreateForm, CommentForm, EditProfileForm
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Count
from django.http import Http404


class PostListView(ListView):
    model = Post
    template_name = 'blog/index.html'
    paginate_by = settings.POSTS_PER_PAGE

    def get_queryset(self):
        return filter_published_posts(get_annotated_posts_queryset())


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'
    pk_url_kwarg = 'post_id'

    def get_object(self, queryset=None):

        post = get_object_or_404(Post, pk=self.kwargs['post_id'])

        if post.author != self.request.user:
            if not post.is_published:
                raise Http404("Пост не опубликован")
            if post.pub_date > timezone.now():
                raise Http404('Пост пока что не опубликован')
            if not post.category.is_published:
                raise Http404('Категория поста не опубликована')

        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['comments'] = (self.object
                               .comments
                               .select_related('author')
                               .all())
        if self.request.user.is_authenticated:
            context['form'] = CommentForm()
        return context


class CategoryPostListView(ListView):
    model = Post
    template_name = 'blog/category.html'
    paginate_by = settings.POSTS_PER_PAGE

    def get_queryset(self):
        category_slug = self.kwargs['category_slug']
        self.category = get_object_or_404(
            Category,
            slug=category_slug,
            is_published=True
        )
        qs = self.category.posts.all()
        return filter_published_posts(get_annotated_posts_queryset(qs))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostCreateForm
    template_name = 'blog/create.html'

    def form_valid(self, form):
        form.instance.author = self.request.user
        response = super().form_valid(form)
        return response

    def get_success_url(self):
        username = self.request.user.username
        return reverse('blog:profile', kwargs={'username': username})


class PostEditView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostCreateForm
    template_name = 'blog/create.html'
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.author != request.user:
            return redirect('blog:post_detail', post_id=self.object.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse(
            'blog:post_detail',
            kwargs={'post_id': self.kwargs['post_id']}
        )


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    template_name = 'blog/create.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        if obj.author != request.user:
            return redirect('blog:post_detail', post_id=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        return context

    def get_success_url(self):
        return reverse(
            'blog:profile',
            kwargs={'username': self.request.user.username})


User = get_user_model()


class RegisterView(CreateView):
    form_class = UserCreationForm
    template_name = 'registration/registration_form.html'
    success_url = reverse_lazy('blog:index')


class ProfileDetailView(DetailView):
    model = User
    template_name = 'blog/profile.html'
    context_object_name = 'profile'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile_user = self.get_object()

        qs = profile_user.posts.select_related('category')

        if self.request.user != profile_user:
            qs = filter_published_posts(qs)

        qs = qs.annotate(comment_count=Count('comments')).order_by('-pub_date')

        context['page_obj'] = get_paginated_page(
            self.request, qs, settings.POSTS_PER_PAGE
        )
        context['is_owner'] = (self.request.user.is_authenticated
                               and self.request.user == profile_user)
        return context


class EditProfileView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = EditProfileForm
    template_name = 'blog/user.html'
    context_object_name = 'profile'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse('blog:profile',
                       kwargs={'username': self.request.user.username})


class CommentCreateView(LoginRequiredMixin, CreateView):
    model = Comment
    form_class = CommentForm
    template_name = 'blog/detail.html'
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        self.post_obj = get_object_or_404(Post, pk=kwargs['post_id'])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['post'] = self.post_obj
        ctx['comments'] = self.post_obj.comments.select_related('author').all()
        return ctx

    def form_valid(self, form):
        form.instance.post = self.post_obj
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'blog:post_detail',
            kwargs={'post_id': self.post_obj.pk}
        ) + '#comments'


class CommentBase(LoginRequiredMixin):
    model = Comment

    def get_success_url(self):
        comment = self.get_object()
        return reverse('blog:post_detail',
                       kwargs={'post_id': comment.post.pk}) + '#comments'

    def get_queryset(self):
        return self.model.objects.filter(author=self.request.user)


class CommentUpdateView(CommentBase, UpdateView):
    template_name = 'blog/comment.html'
    form_class = CommentForm
    pk_url_kwarg = 'comment_id'

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(post__pk=self.kwargs['post_id'])


class CommentDeleteView(CommentBase, DeleteView):
    template_name = 'blog/comment.html'

    def get_object(self, queryset=None):
        queryset = self.get_queryset()
        comment_id = self.kwargs.get('comment_id')
        post_id = self.kwargs.get('post_id')
        obj = get_object_or_404(queryset, pk=comment_id, post__pk=post_id)
        return obj


def filter_published_posts(queryset=None):
    if queryset is None:
        queryset = Post.objects.all()
    return queryset.filter(
        is_published=True,
        pub_date__lte=timezone.now(),
        category__is_published=True
    )


def get_paginated_page(request, queryset, per_page):
    paginator = Paginator(queryset, per_page)
    page = request.GET.get('page')
    try:
        paginated_posts = paginator.page(page)
    except PageNotAnInteger:
        paginated_posts = paginator.page(1)
    except EmptyPage:
        paginated_posts = paginator.page(paginator.num_pages)

    return paginated_posts


def get_annotated_posts_queryset(queryset=None):
    if queryset is None:
        queryset = Post.objects.all()
    return queryset.select_related(
        'category', 'location', 'author'
    ).annotate(
        comment_count=Count('comments')
    ).order_by('-pub_date')
