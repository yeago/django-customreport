import datetime

from django.db import models

class Report(models.Model):
	fields = models.TextField()
	parameters = models.TextField(null=True,blank=True)
	columns = models.TextField()
	date_added = models.DateTimeField(default=datetime.datetime.now)
	added_by = models.ForeignKey('auth.User')
