# Copyright 2020; Raja Tomar
# See license for more details
import os
import logging
from operator import attrgetter

from .elements import HTMLResource
from .schedulers import default_scheduler
from .schedulers import crawler_scheduler
from .session import check_connection
from .urls import parse_url

__all__ = ['WebPage', 'Crawler']

logger = logging.getLogger(__name__)


class WebPage(HTMLResource):
    @classmethod
    def from_config(cls, config):
        if config and not config.is_set():
            raise AttributeError("Configuration is not setup.")

        session = config.create_session()
        scheduler = default_scheduler()
        context = config.create_context()
        ans = cls(session, config, scheduler, context)
        url = parse_url(config.get('project_url'))
        if check_connection(url.hostname, url.port, 0.01):
            ans.get(config.get('project_url'))
        return ans

    def __repr__(self):
        return '<WebPage: [%s]>' % getattr(self.response, 'url', 'None')

    element_map = property(
        attrgetter('scheduler.data'),
        doc="Registry of different handler for different tags."
    )

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
        with open(filename, 'wb') as fh:
            source, enc = self.get_source()
            fh.write(source)

    def save_complete(self, pop=False):
        """Saves the complete html+assets on page to a file and
        also writes its linked files to the disk.

        Implements the combined logic of save_assets and save_html in
        compact form with checks and validation.
        """
        if not self.viewing_html():
            raise ValueError("Not viewing a html page. Please check the link!")

        #: NOTE Start with indexing self
        # self.scheduler.index.add_resource(self)

        self.scheduler.handle_resource(self)
        if pop and os.path.exists(self.filepath):
            self.logger.info(
                "Opening default browser with file: %s" % self.filepath)
            import webbrowser
            webbrowser.open('file:///' + self.filepath)

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
        url = parse_url(config.get('project_url'))
        if check_connection(url.hostname, url.port, 0.01):
            ans.get(config.get('project_url'))
        return ans
