from django.conf import settings

class ReportSite(object):
	def __init__(self):
		self.non_filter_fields = ['submit','filter_fields','custom_token','custom_modules','display_fields']

	def get_urls(self):
		from django.conf.urls.defaults import patterns, url, include

		"""
		if settings.DEBUG:
			self.check_dependencies()
		"""

		def wrap(view, cacheable=False):
			def wrapper(*args, **kwargs):
				return self.admin_view(view, cacheable)(*args, **kwargs)
			return update_wrapper(wrapper, view)

		# Admin-site-wide views.
		reportpatterns = patterns('',
			url(r'^fields/$',
				wrap(self.fields, cacheable=True),
				name='fields'),
			url(r'^filters/$',
				wrap(self.filters, cacheable=True),
				name='filters'),
			url(r'^columns/$',
				wrap(self.columns, cacheable=True),
				name='columns'),
			url(r'^results/$',
				wrap(self.results, cacheable=True),
				name='results'),
			url(r'^save/$',
				wrap(self.results, cacheable=True),
				name='results'),
		)

		storedreport_patterns = patterns('',
			url(r'^recall/$',
				wrap(self.recall, cacheable=True),
				name='recall'),
			url(r'',include(report_patterns)),
		)

		urlpatterns = reportpatterns + patterns('',
			url(r'^$',
				wrap(self.index),
				name='index'),
			url(r'^(?P<report_id>[^/]+)/',include(storedreport_patterns)),
		)

		return urlpatterns

	def urls(self):
		return self.get_urls(), self.app_name, self.name
	urls = property(urls)

	def get_fields_form(self,request):
		from django_customreport.forms import FilterSetCustomFieldsForm
		return FilterSetCustomFieldsForm(self.filter,request.GET or None)

	def get_filter_form(self):
		return self.filter.form

	def get_queryset(self):
		return self.filter.queryset

	def get_results(self,queryset,display_fields=None):
		filter = self.filterset_class(self.request.GET,queryset=queryset)
		return super(displayset_view,self).get_results(filter.qs,display_fields=display_fields)

	def save(self,request,report_id=None):
		pass

	def recall(self,request,report_id=None):
		pass

	def fields(self,request,report_id=None):
		form = cls.get_fields_form(request)
		if request.GET and form.is_valid():
			request.SESSION['report_filter_fields'] = form.cleaned_data.get['filter_fields']
			return redirect("../filter/")

		return render_to_response("/customreport/fields_form.html", {'form': form}, \
			context_instance=RequestContext(request))

	def filters(self,request,report_id=None):
		kept_filters = self.filter.filters.copy()
		for i in self.filter.filters:
			if not i in request.SESSION['report_filter_fields']:
				del kept_filters[i]

		self.filter.filters = kept_filters
		
		filter_fields = filter_fields or []

		form = self.get_post_form()
		
		form.fields = kept_fields
	
		from django import forms
		if self.request.POST and form.is_valid():
			request.SESSION['report_filter_criteria'] = form.cleaned_data
			return redirect("../results/")

		return render_to_response(some_template,{"form": form},context_instance=RequestContext(request))

	def columns(self,report_id=None):
		return render_to_response(some_template,{'form': self.get_column_form()},context=RequestContext(request))
		
	def results(self,report_id=None):
		queryset = self.get_results(self.queryset,display_fields=request.SESSION.get('report_display_fields'))
		self.displayset_class.display_fields = display_fields

		"""
		Refactor this to work more like admin actions.

		if self.request.GET.get('custom_modules',None):
			if self.modules[self.request.GET.get('custom_modules')]:
				return self.modules[self.request.GET.get('custom_modules')](self.request,queryset,extra_context=self.extra_context)

		"""

		from django_displayset import views as displayset_views
		return displayset_views.filterset_generic(self.request,self.filter,self.displayset_class,\
				queryset=queryset,extra_context=self.extra_context)
