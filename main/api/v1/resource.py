# coding: utf-8

from __future__ import absolute_import

import json
from google.appengine.api import images
from google.appengine.ext import blobstore
from google.appengine.ext import ndb
import flask
import flask_cors
import flask_restful
import werkzeug

import email
from api import helpers
import auth
import config
import model
import util

from main import api_v1

from googleapiclient import discovery
from oauth2client.client import GoogleCredentials
credentials = GoogleCredentials.get_application_default()
storage = discovery.build('storage', 'v1', credentials=credentials)

###############################################################################
# Endpoints
###############################################################################
@api_v1.resource('/resource/', endpoint='api.resource.list')
class ResourceListAPI(flask_restful.Resource):
  @auth.admin_required
  def get(self):
    resource_keys = util.param('resource_keys', list)
    if resource_keys:
      resource_db_keys = [ndb.Key(urlsafe=k) for k in resource_keys]
      resource_dbs = ndb.get_multi(resource_db_keys)
      return helpers.make_response(resource_dbs, model.Resource.FIELDS)

    resource_dbs, next_cursor = model.Resource.get_dbs()
    return helpers.make_response(
        resource_dbs, model.Resource.FIELDS, next_cursor,
      )

  @auth.admin_required
  def delete(self):
    resource_keys = util.param('resource_keys', list)
    if not resource_keys:
      helpers.make_not_found_exception(
          'Resource(s) %s not found' % resource_keys
        )
    resource_db_keys = [ndb.Key(urlsafe=k) for k in resource_keys]
    delete_resource_dbs(resource_db_keys)
    return flask.jsonify({
        'result': resource_keys,
        'status': 'success',
      })


@api_v1.resource('/resource/<string:key>/', endpoint='api.resource')
class ResourceAPI(flask_restful.Resource):
  @auth.admin_required
  def get(self, key):
    resource_db = ndb.Key(urlsafe=key).get()
    if not resource_db:
      helpers.make_not_found_exception('Resource %s not found' % key)
    return helpers.make_response(resource_db, model.Resource.FIELDS)

  @auth.admin_required
  def delete(self, key):
    resource_db = ndb.Key(urlsafe=key).get()
    if not resource_db:
      helpers.make_not_found_exception('Resource %s not found' % key)
    delete_resource_key(resource_db.key)
    return helpers.make_response(resource_db, model.Resource.FIELDS)


def extract_cloud_storage_meta_data(file_storage):
  """ Exctract the cloud storage meta data from a file. """
  uploaded_headers = _format_email_headers(file_storage.read())
  storage_object_url = uploaded_headers.get(blobstore.CLOUD_STORAGE_OBJECT_HEADER, None)
  return tuple(_split_storage_url(storage_object_url))

def _format_email_headers(raw_headers):
  """ Returns an email message containing the headers from the raw_headers. """
  message = email.message.Message()
  message.set_payload(raw_headers)
  payload = message.get_payload(decode=True)
  return email.message_from_string(payload)

def _split_storage_url(storage_object_url):
  """ Returns a list containing the bucket id and the object id. """
  return storage_object_url.split("/")[2:]


@api_v1.resource('/resource/upload/', endpoint='api.resource.upload')
class ResourceUploadAPI(flask_restful.Resource):

  @flask_cors.cross_origin()
  def options(self):
    return flask.jsonify({})

  @flask_cors.cross_origin()
  def get(self):
    count = util.param('count', int) or 1
    urls = []
    for i in range(count):
      urls.append({'upload_url': blobstore.create_upload_url(
          flask.request.path,
          gs_bucket_name=get_bucket_and_path_name() or None,
        )})
    return flask.jsonify({
        'status': 'success',
        'count': count,
        'result': urls,
      })

  @flask_cors.cross_origin()
  def post(self):
    resource_db = resource_db_from_upload()
    if resource_db:
      return helpers.make_response(resource_db, model.Resource.FIELDS)
    flask.abort(500)


###############################################################################
# Helpers
###############################################################################
@ndb.transactional(xg=True)
def delete_resource_dbs(resource_db_keys):
  for resource_key in resource_db_keys:
    delete_resource_key(resource_key)


def delete_resource_key(resource_key):
  resource_db = resource_key.get()
  if resource_db:
    blobstore.BlobInfo.get(resource_db.blob_key).delete()
    resource_db.key.delete()


def resource_db_from_upload():
  try:
    uploaded_file = flask.request.files['file']
  except:
    return None

  bucket_name, origin_dir, object_name = extract_cloud_storage_meta_data(uploaded_file)
  headers = uploaded_file.headers['Content-Type']
  blob_info_key = werkzeug.parse_options_header(headers)[1]['blob-key']
  blob_info = blobstore.BlobInfo.get(blob_info_key)

  gcs_object_path = "{}/{}/{}".format(bucket_name, origin_dir, object_name)
  image_url = None
  public_url = None
  if blob_info.content_type.startswith('image'):
    try:
      image_url = images.get_serving_url(blob_info.key(), secure_url=True)
    except:
      pass
  else:
    response = storage.objects().patch(
        bucket=bucket_name,
        object="{}/{}".format(origin_dir, object_name),
        body={'acl': [{
          "entity": "project-owners-825037505474",
          "role": "OWNER",
        }, {
          "entity": "project-editors-825037505474",
          "role": "OWNER",
        }, {
          "entity": "project-viewers-825037505474",
          "role": "READER",
        },{
          "entity": "allUsers",
          "READER",
        }]}).execute()
    public_url = "https://storage.googleapis.com/{}?content_type={}".format(
        gcs_object_path, blob_info.content_type)

  resource_db = model.Resource(
      user_key=auth.current_user_key(),
      blob_key=blob_info.key(),
      name=blob_info.filename,
      content_type=blob_info.content_type,
      size=blob_info.size,
      image_url=image_url,
      public_url=public_url,
      bucket_name=get_bucket_and_path_name() or None,
      gcs_object_path=gcs_object_path,
    )
  resource_db.put()
  return resource_db

def get_bucket_and_path_name():
  origin = flask.request.headers.get('origin')
  if origin:
    origin = origin.replace('https://', '').replace('http://', '')
  bucket = '{}/{}'.format(config.CONFIG_DB.bucket_name, origin or 'no-origin')
  return bucket
