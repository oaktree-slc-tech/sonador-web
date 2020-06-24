from guru.views import GuruApiObjectManagementView, GuruApiRestView
from guru.helpers.compatability import guru_page_not_found

from ..models.servers import PacsImagingServer
from .base import SonadorApiObjectManagementView, SonadorApiRestView


class PacsImagingServerChildObjectMixin(object):
	'''	Mixin object which provides methods for retrieving objects associated with
		an imaging server.
	'''
	request_serverid_fieldname = 'serverid'

	def getServer(self, request=None, vargs=None, vkwargs=None):
		'''	Retrieve the imaging server the child objects are associated with
		'''
		vkwargs = vkwargs or {}

		# Check view server keyword arguments for a cached server, return if present
		if vkwargs.get('server'): return vkwargs.get('server')

		# Retrieve server from database, cache a copy
		server = PacsImagingServer.objects.get(pk=vkwargs.get(self.request_serverid_fieldname))
		vkwargs['server'] = server

		return server

	def setObjectServer(self, request, forminstance, vargs=None, vkwargs=None):
		'''	Set the server instance for the object as part of the save routine.
		'''
		server = self.getServer(request=request, vargs=vargs, vkwargs=vkwargs)
		setattr(forminstance.instance, 'server', server)

	def saveObjectData(self, request, forminstance, vargs=None, vkwargs=None):
		'''	Save the object data via the forminstance and attach the server associated with the view
		'''
		self.setObjectServer(request, forminstance, vargs=vargs, vkwargs=vkwargs)
		return super(PacsImagingServerChildObjectMixin, self).saveObjectData(
			request, forminstance, vargs=vargs, vkwargs=vkwargs)

	def get(self, request, *args, **kwargs):
		try: server = self.getServer(request, vargs=args, vkwargs=kwargs)
		except PacsImagingServer.DoesNotExist as err: return guru_page_not_found(request, err)

		return super(PacsImagingServerChildObjectMixin, self).get(request, *args, **kwargs)


class PacsImagingServerChildObjectManagementView(PacsImagingServerChildObjectMixin, SonadorApiObjectManagementView):
	'''	Object management view used to work with imaging server child models.
	'''
	def getQueryset(self, request=None, vargs=None, vkwargs=None):
		'''	Retrieve the child objects associated with a specific imaging server
		'''
		queryset = super(PacsImagingServerChildObjectManagementView, self).getQueryset(
			request=request, vargs=vargs, vkwargs=vkwargs)
		return queryset.filter(server=self.getServer(request=request, vargs=vargs, vkwargs=vkwargs))


class PacsImagingServerChildObjectRestView(PacsImagingServerChildObjectMixin, SonadorApiRestView):
	'''	Object REST view used to work with imaging server child models.
	'''
	def getObjectManager(self, request=None, vargs=None, vkwargs=None):
		'''	Retrieve the children associated with the server view
		'''
		server = self.getServer(request=request, vargs=vargs, vkwargs=vkwargs)
		omanager = super(PacsImagingServerChildObjectRestView, self).getObjectManager(
			request=request, vargs=vargs, vkwargs=vkwargs)
		return omanager.filter(server=server)
