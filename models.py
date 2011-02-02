import datetime

from django.db import models
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
	data = DataField(null=True,blank=True,editable=False) # Serialized dict
	app_label = models.CharField(max_length=30,editable=False)
	name = models.CharField(max_length=30,null=True,blank=True,help_text="User specified name for report")
	date_added = models.DateTimeField(default=datetime.datetime.now,editable=False)
	added_by = models.ForeignKey('auth.User')
