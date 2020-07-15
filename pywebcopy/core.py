# Copyright 2020; Raja Tomar
# See license for more details
import logging
import os
from operator import attrgetter

from lxml.html import HTMLParser
from lxml.html import XHTML_NAMESPACE
from lxml.html import parse

from .elements import HTMLResource
from .schedulers import crawler_scheduler
from .schedulers import default_scheduler

__all__ = ['WebPage', 'Crawler']

logger = logging.getLogger(__name__)


class State(object):
    """Used by :class:`WebPage` to store current resource content
    to minimize the number of requests made while working with a page.
    """

    @classmethod
    def from_response(cls, response):
        raise NotImplementedError()

    def read(self, n=None):
        raise NotImplementedError()


class WebPage(HTMLResource):
    @classmethod
    def from_config(cls, config):
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        session = config.create_session()
        scheduler = default_scheduler()
        context = config.create_context()
        ans = cls(session, config, scheduler, context)
        # url = parse_url(config.get('project_url'))
        # if check_connection(url.hostname, url.port, 0.01):
        #     ans.get(config.get('project_url'))
        return ans

    def __repr__(self):
        return '<WebPage: [%s]>' % getattr(self.response, 'url', 'None')

    element_map = property(
        attrgetter('scheduler.data'),
        doc="Registry of different handler for different tags."
    )

    def get_forms(self):
        """Returns a list of form elements available on the page."""
        source, encoding = super(HTMLResource, self).get_source(raw_fp=True)
        return parse(
            source, parser=HTMLParser(encoding=encoding, collect_ids=False)
        ).xpath(
            "descendant-or-self::form|descendant-or-self::x:form",
            namespaces={'x': XHTML_NAMESPACE}
        )

    def submit_form(self, form, **extra_values):
        """
        Helper function to submit a form.

        .. todo::
            check documentation.

        You can use this like::

            wp = WebPage()
            wp.get('http://httpbin.org/forms/')
            form = wp.get_forms()[0]
            form.inputs['email'].value = 'bar' # etc
            form.inputs['password'].value = 'baz' # etc
            wp.submit_form(form)
            wp.get_links()

        The action is one of 'GET' or 'POST', the URL is the target URL as a
        string, and the values are a sequence of ``(name, value)`` tuples with the
        form data.
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
        scheduler = crawler_scheduler()
        context = config.create_context()
        ans = cls(session, config, scheduler, context)
        # url = parse_url(config.get('project_url'))
        # if check_connection(url.hostname, url.port, 0.01):
        #     ans.get(config.get('project_url'))
        return ans
