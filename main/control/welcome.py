# coding: utf-8

import logging

import flask

import config
import util
import model
import task

from main import app
from auth import auth

###############################################################################
# Welcome
###############################################################################
@app.route('/')
def welcome():
  form = auth.form_with_recaptcha(auth.SignUpForm())
  return flask.render_template(
    'welcome.html',
    html_class='welcome',
    form=form)


@app.route('/subscribe/', methods=['POST'])
def subscribe():
  form = auth.form_with_recaptcha(auth.SignUpForm())
  logging.error('WHAT %s', form.validate())
  if form.validate_on_submit():
    logging.error('WHAT')
    user_db = model.User.get_by('email', form.email.data)
    if user_db:
      logging.error('WHAT')
      form.email.errors.append('This email is already subscribed.')

    if not form.errors:
      logging.error('WHAT')
      user_db = auth.create_user_db(
        None,
        util.create_name_from_email(form.email.data),
        form.email.data,
        form.email.data,
      )
      user_db.put()
      task.subscribe_email_notification(user_db)

  return flask.redirect(flask.url_for('welcome'))



###############################################################################
# Sitemap stuff
###############################################################################
@app.route('/sitemap.xml')
def sitemap():
  response = flask.make_response(flask.render_template(
    'sitemap.xml',
    lastmod=config.CURRENT_VERSION_DATE.strftime('%Y-%m-%d'),
  ))
  response.headers['Content-Type'] = 'application/xml'
  return response


###############################################################################
# Warmup request
###############################################################################
@app.route('/_ah/warmup')
def warmup():
  # TODO: put your warmup code here
  return 'success'
