# Copyright 2020; Raja Tomar
# See license for more details
import logging
import operator
import os

from lxml.html import HTMLParser
from lxml.html import XHTML_NAMESPACE
from lxml.html import parse
from requests.models import Response

from .elements import HTMLResource
from .helpers import RewindableResponse
from .schedulers import crawler_scheduler
from .schedulers import default_scheduler
from .schedulers import threading_crawler_scheduler
from .schedulers import threading_default_scheduler

__all__ = ['WebPage', 'Crawler']

logger = logging.getLogger(__name__)


class WebPage(HTMLResource):
    @classmethod
    def from_config(cls, config):
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        session = config.create_session()
        if config.get('threaded'):
            scheduler = threading_default_scheduler()
        else:
            scheduler = default_scheduler()
        context = config.create_context()
        ans = cls(session, config, scheduler, context)
        # url = parse_url(config.get('project_url'))
        # if check_connection(url.hostname, url.port, 0.01):
        #     ans.get(config.get('project_url'))
        return ans

    def __str__(self):
        return '<{}: {}>'.format(self.__class__.__name__, self.url)

    element_map = property(
        operator.attrgetter('scheduler.data'),
        doc="Registry of different handler for different tags."
    )

    def set_response(self, response):
        if not isinstance(response, Response):
            raise ValueError(
                "Expected %r, got %r" % (Response, response))
        # Wrap the response file with a wrapper that will cache the
        #   response when the stream has been consumed.
        # urllib_response = response.raw
        # urllib_response._fp = CallbackFileWrapper(
        #     urllib_response._fp,
        #     urllib_response.release_conn,
        # )
        # if urllib_response.chunked:
        #     super_update_chunk_length = urllib_response._update_chunk_length
        #
        #     def _update_chunk_length(s):
        #         super_update_chunk_length()
        #         if s.chunk_left == 0:
        #             s._fp.close()
        #
        #     urllib_response._update_chunk_length = types.MethodType(
        #         _update_chunk_length, urllib_response
        #     )
        response.raw.decode_content = True
        response.raw = RewindableResponse(response.raw)
        return super(WebPage, self).set_response(response)

    def get_source(self, buffered=False):
        """Returns a rewindable io wrapper.
        """
        raw = getattr(self.response, 'raw', None)
        if raw is None:
            raise ValueError("HTTP Response is not set!")

        # if raw.closed:
        #     raise ValueError(
        #         "I/O operations are closed for the raw source.")

        # Return the raw object which will decode the
        # buffer while reading otherwise errors will follow
        raw.decode_content = True

        # fp = getattr(raw, '_fp', None)
        # assert fp is not None, "Raw source wrapper is missing!"
        # assert isinstance(fp, CallbackFileWrapper), \
        #     "Raw source wrapper is missing!"
        raw.rewind()
        if buffered:
            return raw, self.encoding
        return raw.read(), self.encoding

    def refresh(self):
        raise NotImplementedError()
        # self.set_response(self.session.get(self.url, stream=True))

    def get_forms(self):
        """Returns a list of form elements available on the page."""
        source, encoding = self.get_source(buffered=True)
        return parse(
            source, parser=HTMLParser(encoding=encoding, collect_ids=False)
        ).xpath(
            "descendant-or-self::form|descendant-or-self::x:form",
            namespaces={'x': XHTML_NAMESPACE}
        )

    def submit_form(self, form, **extra_values):
        """
        Helper function to submit a form.

        You can use this like::

            wp = WebPage()
            wp.get('http://httpbin.org/forms/')
            form = wp.get_forms()[0]
            form.inputs['email'].value = 'bar' # etc
            form.inputs['password'].value = 'baz' # etc
            wp.submit_form(form)
            wp.get_links()

        The action is one of 'GET' or 'POST', the URL is the target URL as a
        string, and the values are a sequence of ``(name, value)`` tuples
        with the form data.
        """
        values = form.form_values()
        if extra_values:
            if hasattr(extra_values, 'items'):
                extra_values = extra_values.items()
            values.extend(extra_values)

        if form.action:
            url = form.action
        elif form.base_url:
            url = form.base_url
        else:
            url = self.url
        return self.request(form.method, url, data=values)

    def get_files(self):
        return (e[2] for e in self.parse())

    def get_links(self):
        return (e[2] for e in self.parse() if e[0].tag == 'a')

    def scrape_html(self, url):
        response = self.session.get(url)
        response.raise_for_status()
        return response.content

    def scrape_links(self, url):
        response = self.session.get(url)
        response.raise_for_status()
        return response.links()

    def save_html(self, filename=None):
        """Saves the html of the page to a default or specified file.

        :param filename: path of the file to write the contents to
        """
        filename = filename or self.filepath
        with open(filename, 'w+b') as fh:
            source, enc = self.get_source()
            fh.write(source)
        return filename

    def save_complete(self, pop=False):
        """Saves the complete html+assets on page to a file and
        also writes its linked files to the disk.

        Implements the combined logic of save_assets and save_html in
        compact form with checks and validation.
        """
        if not self.viewing_html():
            raise TypeError(
                "Not viewing a html page. Please check the link!")

        self.scheduler.handle_resource(self)
        if pop:
            self.open_in_browser()
        return self.filepath

    def open_in_browser(self):
        """Open the page in the default browser if it has been saved.

        You need to use the :meth:`~WebPage.save_complete` to make it work.
        """
        if not os.path.exists(self.filepath):
            self.logger.info(
                "Can't find the file to open in browser: %s" % self.filepath)
            return False

        self.logger.info(
            "Opening default browser with file: %s" % self.filepath)
        import webbrowser
        return webbrowser.open('file:///' + self.filepath)

    # handy shortcuts
    run = crawl = save_assets = save_complete


class Crawler(WebPage):

    @classmethod
    def from_config(cls, config):
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        session = config.create_session()
        if config.get('threaded'):
            scheduler = threading_crawler_scheduler()
        else:
            scheduler = crawler_scheduler()
        context = config.create_context()
        ans = cls(session, config, scheduler, context)
        # url = parse_url(config.get('project_url'))
        # if check_connection(url.hostname, url.port, 0.01):
        #     ans.get(config.get('project_url'))
        return ans
