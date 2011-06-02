import datetime

from django.db import models
from django.core.urlresolvers import reverse
try:
	import cPickle as pickle
except:
	import pickle

import base64

class DataField(models.TextField):
	"""Because Django for some reason feels its needed to repeatedly call
	to_python even after it's been converted this does not support strings."""
	__metaclass__ = models.SubfieldBase

	def to_python(self, value):
		if not value: return
		if not isinstance(value, basestring): return value
		value = pickle.loads(base64.b64decode(value))
		return value

	def get_db_prep_save(self, value):
		if value is None: return
		return base64.b64encode(pickle.dumps(value))

class Report(models.Model):
	description = models.TextField(null=True,blank=True)
	data = DataField(null=True,blank=True,editable=False) # Serialized dict
	app_label = models.CharField(max_length=30,editable=False)
	name = models.CharField(max_length=30,null=True,blank=True,help_text="User specified name for report")
	date_added = models.DateTimeField(default=datetime.datetime.now,editable=False)
	added_by = models.ForeignKey('auth.User')

	def get_absolute_url(self):
		return reverse('%s-report:recall' % self.app_label, args=[self.pk])

	def get_delete_url(self):
		return reverse('%s-report:delete' % self.app_label, args=[self.pk])

	def get_edit_url(self):
		return reverse('%s-report:details' % self.app_label, args=[self.pk])

	def get_reset_url(self):
		return reverse('%s-report:reset' % self.app_label, args=[self.pk])

	def get_fields_url(self):
		return reverse('%s-report:fields' % self.app_label, args=[self,pk])

	class Meta:
		ordering = ['-date_added']

class ReportColumn(models.Model):
	report_site = models.ForeignKey('ReportSite')
	relation = models.TextField(help_text="somerelation__someobject__somefield")
	human_name = models.TextField(null=True,blank=True)
	cardinality = models.PositiveIntegerField(default=0)

class ReportSite(models.Model):
	site_label = models.CharField(unique=True,max_length=255)
