from django.contrib.admin import AdminSite as DjangoAdminSite
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _, gettext_lazy
from django.views.decorators.cache import never_cache


def request_site_context(request):
	'''	`site` and `site_name` for the request's site (`request.site`). Django's own views resolve
		them with `get_current_site`, which raises for an allowed host that has no site of its own.
	'''
	from visionaire.sites import request_site

	site = getattr(request, 'site', None) or request_site(request)
	return { 'site': site, 'site_name': site.name if site else '' }


class SiteLoginView(auth_views.LoginView):

	def get_context_data(self, **kwargs):
		context = super(auth_views.LoginView, self).get_context_data(**kwargs)
		context.update({
			self.redirect_field_name: self.get_redirect_url(),
			**request_site_context(self.request),
			**(self.extra_context or {}),
		})
		return context


class SiteLogoutView(auth_views.LogoutView):

	def get_context_data(self, **kwargs):
		context = super(auth_views.LogoutView, self).get_context_data(**kwargs)
		context.update({
			**request_site_context(self.request),
			'title': _('Logged out'),
			'subtitle': None,
			**(self.extra_context or {}),
		})
		return context


class SonadorAdminSite(DjangoAdminSite):
	'''	Django backend admin site for Sonador

		Login and logout are Django's (5.2) with the site taken from the request, so the admin
		works on every allowed host whether or not it has a site of its own.
	'''
	site_title = gettext_lazy('Sonador')
	site_header = gettext_lazy('Sonador Administration')
	index_title = gettext_lazy('Administration')

	def logout(self, request, extra_context=None):
		defaults = {
			'extra_context': {
				**self.each_context(request),
				'has_permission': False,
				**(extra_context or {}),
			},
		}
		if self.logout_template is not None:
			defaults['template_name'] = self.logout_template
		request.current_app = self.name
		return SiteLogoutView.as_view(**defaults)(request)

	@method_decorator(never_cache)
	@login_not_required
	def login(self, request, extra_context=None):
		if request.method == 'GET' and self.has_permission(request):
			return HttpResponseRedirect(reverse('admin:index', current_app=self.name))

		from django.contrib.admin.forms import AdminAuthenticationForm

		context = {
			**self.each_context(request),
			'title': _('Log in'),
			'subtitle': None,
			'app_path': request.get_full_path(),
			'username': request.user.get_username(),
		}
		if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
			context[REDIRECT_FIELD_NAME] = reverse('admin:index', current_app=self.name)
		context.update(extra_context or {})

		defaults = {
			'extra_context': context,
			'authentication_form': self.login_form or AdminAuthenticationForm,
			'template_name': self.login_template or 'admin/login.html',
		}
		request.current_app = self.name
		return SiteLoginView.as_view(**defaults)(request)
