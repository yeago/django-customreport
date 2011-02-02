from django.conf import settings
from django.utils.functional import update_wrapper
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext

from django.core.urlresolvers import reverse

from django.contrib import messages

from django_customreport.helpers import process_queryset

from django_customreport.models import Report

class ReportSite(object):
	app_name = "None"
	name = "None"

	def __init__(self):
		self.non_filter_fields = ['submit','filter_fields','custom_token','custom_modules','display_fields']
		self.fields_template = getattr(self,'fields_template','customreport/fields_form.html')
		self.filters_template = getattr(self,'filters_template','customreport/filters_form.html')
		self.columns_template = getattr(self,'fields_template','customreport/column_form.html')
		self.display_field_inclusions = getattr(self,'display_field_inclusions',None) or []
		self.display_field_exclusions = getattr(self,'display_field_exclusions',None) or []

		if not hasattr(self,'app_label'):
			self.app_label = self.queryset.model._meta.verbose_name

		self.name = self.app_label

	def report_view(self, view, cacheable=False):
		def inner(request, *args, **kwargs):
			return view(request, *args, **kwargs)
		if not cacheable:
			inner = never_cache(inner)
		# We add csrf_protect here so this function can be used as a utility
		# function for any view, without having to repeat 'csrf_protect'.
		if not getattr(view, 'csrf_exempt', False):
			inner = csrf_protect(inner)
		return update_wrapper(inner, view)

	def get_urls(self):
		from django.conf.urls.defaults import patterns, url, include
		"""
		if settings.DEBUG:
			self.check_dependencies()
		"""

		def wrap(view, cacheable=False):
			def wrapper(*args, **kwargs):
				return self.report_view(view, cacheable)(*args, **kwargs)
			return update_wrapper(wrapper, view)

		# Admin-site-wide views.
		report_patterns = patterns('',
			url(r'^fields/$',
				wrap(self.fields, cacheable=True),
				name='%s_fields' % self.app_label),
			url(r'^filters/$',
				wrap(self.filters, cacheable=True),
				name='%s_filters' % self.app_label),
			url(r'^columns/$',
				wrap(self.columns, cacheable=True),
				name='%s_columns' % self.app_label),
			url(r'^results/$',
				wrap(self.results, cacheable=True),
				name='%s_results' % self.app_label),
			url(r'^save/$',
				wrap(self.save, cacheable=True),
				name='%s_save' % self.app_label),
		)

		storedreport_patterns = patterns('',
			url(r'^recall/$',
				wrap(self.recall, cacheable=True),
				name='%s_recall' % self.app_label),
			url(r'',include(report_patterns)),
		)

		urlpatterns = report_patterns + patterns('',
			url(r'^$',
				wrap(self.fields),
				name='%s_index' % self.app_label),
			url(r'^reset/$',
				wrap(self.reset, cacheable=True),
				name='%s_reset' % self.app_label),
			url(r'^(?P<report_id>[^/]+)/',include(storedreport_patterns)),
		)

		return urlpatterns

	def urls(self):
		return self.get_urls(), "report", self.app_label
	
	urls = property(urls)

	def get_queryset(self):
		return self.queryset

	def get_fields_form(self,request):
		from django_customreport.forms import FilterSetCustomFieldsForm
		filter = self.filterset_class()
		return FilterSetCustomFieldsForm(filter,request.GET or None)
	
	def get_columns_form(self,request):
		from django_customreport.forms import QueryForm
		return QueryForm(self.get_queryset(),request,depth=self.display_field_depth,
				exclusions=self.display_field_exclusions,inclusions=self.display_field_inclusions,\
				non_filter_fields=self.non_filter_fields)

	def get_results(self,request,queryset,display_fields=None):
		filter = self.filterset_class(request.session.get('report:%s_filter_criteria' % self.app_label),queryset=queryset)
		return process_queryset(filter.qs,display_fields=display_fields)

	def reset(self,request):
		for i in ['filter_fields','filter_criteria','filter_GET','columns']:
			if request.session.get('report:%s_%s' % (self.app_label,i)):
				del request.session['report:%s_%s' % (self.app_label,i)]

		return redirect("report:%s_index" % self.app_label)

	def save(self,request,report_id=None):
		data = {}
		for i in ['filter_fields','filter_criteria','filter_GET','columns']:
			data[i] = request.session.get("report:%s_%s" % (self.app_label,i))

		if report_id and not request.GET.get("as_new"):
			report = get_object_or_404(Report,app_label=self.name,pk=report_id)
			report.data = data
			report.save()

		else:
			report = Report.objects.create(app_label=self.app_label,data=data,added_by=request.user)

		messages.success(request,"Your report has been saved")

		return redirect(request.GET.get('return_ur') or reverse("report:%s_results" % self.app_label,args=[report.pk]))

	def recall(self,request,report_id):
		report = get_object_or_404(Report,app_label=self.name,pk=report_id)
		for k, v in report.data.iteritems():
			request.session[k] = v

		return redirect("report:%s_results" % self.app_label)

	def fields(self,request,report_id=None):
		form = self.get_fields_form(request)
		form.initial.update({'filter_fields': request.session.get('report:%s_filter_fields' % self.app_label)})
		if request.GET and form.is_valid():
			request.session['report:%s_filter_fields' % self.app_label] = form.cleaned_data.get('filter_fields')
			return redirect(reverse("report:%s_filters" % self.app_label))

		return render_to_response(self.fields_template, {'form': form}, \
			context_instance=RequestContext(request))

	def filters(self,request,report_id=None):
		if not request.session.get("report:%s_filter_fields" % self.app_label):
			messages.warning(request,"You must choose some fields before filtering")
			return redirect(reverse("report:%s_fields" % self.app_label))
		
		filter = self.filterset_class(request.GET or None,queryset=self.get_queryset())
		kept_filters = filter.filters.copy()
		for i in filter.filters:
			if not i in request.session['report:%s_filter_fields' % self.app_label]:
				del kept_filters[i]

		filter.filters = kept_filters

		form = filter.form
		form.initial.update(request.session.get('report:%s_filter_criteria' % self.app_label) or {})

		kept_fields = form.fields.copy()
		for i in form.fields:
			if not i in request.session['report:%s_filter_fields' % self.app_label]:
				del kept_fields[i]

		form.fields = kept_fields
		
		if request.GET and form.is_valid():
			request.session['report:%s_filter_criteria' % self.app_label] = form.cleaned_data
			request.session['report:%s_filter_GET' % self.app_label] = request.GET
			return redirect(reverse("report:%s_results" % self.app_label))

		return render_to_response(self.filters_template, {"form": form }, context_instance=RequestContext(request))

	def columns(self,request,report_id=None):
		form = self.get_columns_form(request)
		if request.GET and form.is_valid():
			request.session['report:%s_columns'] = form.cleaned_data.get('display_fields') 
			return redirect(reverse("report:%s_results" % self.app_label))

		return render_to_response(self.columns_template,{'form': form},context_instance=RequestContext(request))

	def results(self,request,report_id=None):
		filter = self.filterset_class(request.session.get('report:%s_filter_GET' % self.app_label),queryset=self.get_queryset())
		display_fields = request.session.get('report:%s_display_fields' % self.app_label) or []
		queryset = self.get_results(request,filter.qs,display_fields=display_fields)
		self.displayset_class.display_fields = display_fields

		"""
		Refactor this to work more like admin actions.

		if self.request.GET.get('custom_modules',None):
			if self.modules[self.request.GET.get('custom_modules')]:
				return self.modules[self.request.GET.get('custom_modules')](self.request,queryset,extra_context=self.extra_context)

		"""

		from django_displayset import views as displayset_views
		return displayset_views.filterset_generic(request,filter,self.displayset_class,\
				queryset=queryset)
