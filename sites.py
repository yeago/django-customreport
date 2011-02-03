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
		self.non_filter_fields = ['submit']
		self.fieldsets = getattr(self,'fieldsets',None)
		self.fields_template = getattr(self,'fields_template','customreport/fields_form.html')
		self.columns_template = getattr(self,'fields_template','customreport/columns_form.html')
		self.index_template = getattr(self,'index_template','customreport/index.html')
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
				name='fields'),
			url(r'^columns/$',
				wrap(self.columns, cacheable=True),
				name='columns'),
			url(r'^results/$',
				wrap(self.results, cacheable=True),
				name='results'),
			url(r'^save/$',
				wrap(self.save, cacheable=True),
				name='save'),
		)

		storedreport_patterns = patterns('',
			url(r'^recall/$',
				wrap(self.recall, cacheable=True),
				name='recall'),
			url(r'',include(report_patterns)),
		)

		urlpatterns = report_patterns + patterns('',
			url(r'^$',
				wrap(self.index),
				name='index'),
			url(r'^reset/$',
				wrap(self.reset, cacheable=True),
				name='reset'),
			url(r'^(?P<report_id>[^/]+)/',include(storedreport_patterns)),
		)

		return urlpatterns

	def urls(self):
		return self.get_urls(), "%s-report" % self.app_label, self.app_label
	urls = property(urls)

	def get_queryset(self):
		return self.queryset

	def get_columns_form(self,request):
		from django_customreport.forms import ColumnForm
		return ColumnForm(self.get_queryset(),request,data=request.GET or None,depth=self.display_field_depth,
				exclusions=self.display_field_exclusions,inclusions=self.display_field_inclusions)

	def get_results(self,request,queryset,display_fields=None):
		filter = self.filterset_class(request.session.get('report:%s_filter_criteria' % self.app_label),queryset=queryset)
		return process_queryset(filter.qs,display_fields=display_fields)

	def reset(self,request):
		for i in ['filter_criteria','filter_GET','columns']:
			if request.session.get('report:%s_%s' % (self.app_label,i)):
				del request.session['report:%s_%s' % (self.app_label,i)]

		return redirect("report:%s_index" % self.app_label)

	def save(self,request,report_id=None):
		data = {}
		for i in ['filter_criteria','filter_GET','columns']:
			data[i] = request.session.get("%s-report:%s" % (self.app_label,i))

		if report_id and not request.GET.get("as_new"):
			report = get_object_or_404(Report,app_label=self.name,pk=report_id)
			report.data = data
			report.save()

		else:
			report = Report.objects.create(app_label=self.app_label,data=data,added_by=request.user)

		messages.success(request,"Your report has been saved")

		return redirect(request.GET.get('return_ur') or reverse("%s-report:results" % self.app_label,args=[report.pk]))

	def recall(self,request,report_id):
		report = get_object_or_404(Report,app_label=self.name,pk=report_id)
		for k, v in report.data.iteritems():
			request.session[k] = v

		return redirect("%s-report:results" % self.app_label)

	def fields(self,request,report_id=None):
		filter = self.filterset_class(request.GET or None,queryset=self.get_queryset())
		"""
		kept_filters = filter.filters.copy()
		for i in filter.filters:
			if not i in request.session['%s-report:filter_fields' % self.app_label]:
				del kept_filters[i]


		filter.filters = kept_filters
		"""
		
		form = filter.form

		form.initial.update(request.session.get('%s-report:filter_criteria' % self.app_label) or {})

		"""

		kept_fields = form.fields.copy()
		for i in form.fields:
			if not i in request.session['%s-report:filter_fields' % self.app_label]:
				del kept_fields[i]

		form.fields = kept_fields

		"""

		if request.GET and form.is_valid():
			request.session['%s-report:filter_criteria' % self.app_label] = form.cleaned_data
			request.session['%s-report:filter_GET' % self.app_label] = request.GET
			return redirect(reverse("%s-report:results" % self.app_label))
		
		fieldsets = []

		if not self.fieldsets:
			fieldsets.append((None,{'fields': [f for f in form] }))

		else:
			accounted_fields = []
	
			for fieldset in self.fieldsets:
				fields = []
				for field_name in fieldset[1]['fields']:
					for field in form:
						if field.name == field_name:
							fields.append(field)

							accounted_fields.append(field_name)
							break

				fieldsets.append((fieldset[0],{'fields': fields}))

			for name, field in form.fields.iteritems():
				if not name in accounted_fields:
					raise ValueError("Unaccounted field %s in fieldset" % name)

		return render_to_response(self.fields_template, {"form": form, "fieldsets": fieldsets }, context_instance=RequestContext(request))

	def columns(self,request,report_id=None):
		form = self.get_columns_form(request)
		form.initial.update({"display_fields": request.session.get("%s-report:columns" % self.app_label)})
		if request.GET and form.is_valid():
			request.session['%s-report:columns' % self.app_label] = form.cleaned_data.get('display_fields')
			return redirect(reverse("%s-report:results" % self.app_label))

		return render_to_response(self.columns_template,{'form': form},context_instance=RequestContext(request))

	def results(self,request,report_id=None):
		filter = self.filterset_class(request.session.get('%s-report:filter_GET' % self.app_label),queryset=self.get_queryset())
		columns = request.session.get('%s-report:columns' % self.app_label) or []
		queryset = self.get_results(request,filter.qs,display_fields=columns)
		self.displayset_class.display_fields = columns

		from django_displayset import views as displayset_views
		return displayset_views.filterset_generic(request,filter,self.displayset_class,\
				queryset=queryset)

	def index(self,request):
		saved_reports = Report.objects.filter(added_by=request.user)
		old_report_session = False
		if request.session.get('report:%s_filter_criteria' % self.app_label, None):
			
			old_report_session = True
		context = {'saved_reports': saved_reports, 'old_report_session': old_report_session}
		return render_to_response(self.index_template, context, context_instance=RequestContext(request))
