# Copyright 2020; Raja Tomar
# See license for more details
import errno
import logging
import os
import re
import warnings
from base64 import b64encode
from contextlib import closing
from datetime import datetime
from functools import partial
from io import BytesIO
from shutil import copyfileobj
from textwrap import dedent

from lxml.html import HtmlComment
from lxml.html import tostring
from six import binary_type
from six import text_type
from six.moves.urllib.request import pathname2url

from .__version__ import __version__
from .helpers import cached_property
from .parsers import iterparse
from .parsers import unquote_match
from .urls import get_content_type_from_headers
from .urls import relate

logger = logging.getLogger(__name__)


def make_fd(location, url=None, overwrite=False):
    # Sub-directories creation
    if not os.path.exists(os.path.dirname(location)):
        try:
            os.makedirs(os.path.dirname(location), mode=0o0700)
        except (OSError, IOError) as e:
            if e.errno != errno.EEXIST:
                logger.error(
                    "[File] Failed to create target location <%r> "
                    "for the file <%r> on the disk." % (location, url)
                )
                return False

    #: low-level System managed io
    try:
        flags = os.O_WRONLY | os.O_CREAT
        if not overwrite:
            flags |= os.O_EXCL
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        if hasattr(os, 'O_BINARY'):
            flags |= os.O_BINARY
        #: open the file
        fd = os.open(location, flags, 0o600)
    except (FileExistsError, PermissionError) as e:
        if (os.name == 'nt' and os.path.isdir(location) and
                os.access(location, os.W_OK)):
            logger.error(
                "Cannot write <%s> to <%s>! %r" % (url, location, e))
            raise e
        else:
            logger.debug("<%s> already exists at: <%s>" % (url, location))
            return False
    else:
        return fd


def retrieve_resource(content, location, url=None, overwrite=False):
    """Renders the downloadable resource to disk.

    :type content: BytesIO
    :param content: file like object with read method
    :param url:
    :param location:
    :param overwrite:
    :return: rendered location or False if failed.
    """
    assert content is not None, "Content can't be of NoneType."
    assert location is not None, "Context can't be of NoneType."
    assert url is not None, "Url can't be of NoneType."

    logger.debug(
        "Preparing to write file from <%r> to the disk at <%r>."
        % (url, location))

    fd = make_fd(location, url, overwrite)
    if not fd:
        return location

    with closing(os.fdopen(fd, 'wb')) as dst:
        copyfileobj(content, dst)

    logger.info("Written the file from <%s> to <%s>" % (url, location))
    return location


class GenericResource(object):
    def __init__(self, session, config, scheduler, context, response=None):
        """
        Generic internet resource which processes a server response based on responses
        content-type. Downloadable file if allowed in config would be downloaded. Css
        file would be parsed using suitable parser. Html will also be parsed using
        suitable html parser.

        :param session: http client used for networking.
        :param config: project configuration handler.
        :param response: http response from the server.
        :param scheduler: response processor scheduler.
        :param context: context of this response; should contain base-location, base-url etc.
        """
        self.session = session
        self.config = config
        self.scheduler = scheduler
        self.context = context
        self.response = None
        if response:
            self.set_response(response)
        self.logger = logger.getChild(self.__class__.__name__)

    def __repr__(self):
        return '<%s(url=%s)>' % (self.__class__.__name__, self.context.url)

    def set_response(self, response):
        """Update the response attribute of this object. Additionally updating the content_type."""
        self.response = response
        #: Clear the cached properties
        self.__dict__.pop('content_type', None)
        self.__dict__.pop('filepath', None)
        self.__dict__.pop('filename', None)
        self.__dict__.pop('url', None)
        self.__dict__.pop('encoding', None)
        self.context = self.context.with_values(
            url=response.url,
            content_type=self.content_type
        )

    @cached_property
    def filepath(self):
        if self.context is None:
            raise AttributeError("Context attribute is not set.")
        if self.response is not None:
            ctypes = get_content_type_from_headers(self.response.headers)
            self.context = self.context.with_values(content_type=ctypes)
        return self.context.resolve()

    @cached_property
    def filename(self):
        return os.path.basename(self.filepath or '')

    @cached_property
    def content_type(self):
        if self.response is not None and 'Content-Type' in self.response.headers:
            return get_content_type_from_headers(self.response.headers)
        raise AttributeError("Response attribute is not set!")

    @cached_property
    def url(self):
        if self.response is not None:
            self.context = self.context.with_values(url=self.response.url)
        return self.context.url

    @cached_property
    def encoding(self):
        if self.response is not None:
            #: Explicit encoding takes precedence
            self.config.get('encoding', self.response.encoding)
        return self.config.get('encoding', 'utf-8')

    valid_html_content_types = tuple([
        'text/htm',
        'text/html',
        'text/xhtml'
    ])

    def viewing_html(self):
        return self.content_type in self.valid_html_content_types

    valid_css_content_types = tuple([
        'text/css'
    ])

    def viewing_css(self):
        return self.content_type in self.valid_css_content_types

    invalid_schemas = tuple([
        'data', 'javascript', 'mailto',
    ])

    def invalid_schema(self, url):
        return url.startswith(self.invalid_schemas)

    def get(self, url, **params):
        """Fetches the Html content from Internet using the requests.
        You can any requests params which will be passed to the library
        itself.
        The requests arguments you supply will also be applied to the
        global session meaning all the files will be downloaded using these
        settings.

        :param url: url of the page to fetch
        :param params: keyword arguments which `requests` module may accept.
        """
        if params.pop('stream', None):
            warnings.warn(UserWarning(
                "Stream attribute is True by default for reasons."
            ))
        self.set_response(self.session.get(url, stream=True, **params))
        self.response.raw.decode_content = True

    def resolve(self, parent_path=None):
        """Calculates the location at which this response should be stored as a file."""
        filepath = self.filepath
        if not isinstance(filepath, text_type):
            raise ValueError("Invalid filepath [%r]" % filepath)
        if parent_path and isinstance(parent_path, text_type):
            return pathname2url(relate(filepath, parent_path))
        return pathname2url(filepath)

    def get_source(self, raw_fp=False):
        assert self.context is not None, "Context not set."
        assert self.context.base_path is not None, "Context Base Path is not set!"
        assert self.context.base_url is not None, "Context Base url is not Set!"
        assert self.response is not None, "Response attribute is not Set!"
        assert hasattr(self.response.raw, 'read'), "Response must have a raw file like object!"

        if raw_fp:
            if hasattr(self.response.raw, 'closed') and self.response.raw.closed:
                if hasattr(self.response, 'from_cache'):
                    if self.response.from_cache:
                        return BytesIO(self.response.content), self.encoding
                #: Re-fetch the content from the server as the connection
                #: has been closed or the stream has exhausted
                self.response = self.session.send(self.response.request)
            self.response.raw.decode_content = True
            return self.response.raw, self.encoding
        return self.response.content, self.encoding

    def retrieve(self):

        if self.response is None:
            raise AttributeError(
                "Response attribute is not set!"
                "You need to fetch the resource using get method!"
            )

        # indexed = self._get_or_set_index()
        # if indexed:
        #     return indexed
        return self._retrieve()

    def _retrieve(self):
        #: Not ok response received from the server
        if not 100 <= self.response.status_code <= 400:
            self.logger.error(
                'Status Code [<%d>] received from the server [%s]'
                % (self.response.status_code, self.response.url)
            )
            if isinstance(self.response.reason, binary_type):
                content = BytesIO(self.response.reason)
            else:
                content = BytesIO(self.response.reason.encode(self.encoding))
        else:
            if not hasattr(self.response, 'raw'):
                self.logger.error("Response object for url <%s> has no attribute 'raw'!" % self.url)
                content = BytesIO(self.response.content)
            else:
                content = self.response.raw

        retrieve_resource(content, self.filepath, self.context.url, self.config.get('overwrite'))
        del content
        return self.filepath

    # def _get_or_set_index(self):
    #     #: Update the index before doing any processing so that later calls
    #     #: in index finds this entry without going in infinite recursion
    #     #: Response could have been already present on disk
    #     indexed = self.scheduler.index.get(self.response.url)
    #     if indexed:
    #         self.logger.debug(
    #             "Resource [%s] is already available in the index at [%s]"
    #             % (self.url, indexed)
    #         )
    #         return indexed
    #     self.scheduler.index[self.context.url] = self.filepath
    #     self.scheduler.index[self.response.url] = self.filepath
    #     for r in self.response.history:
    #         self.scheduler.index[r.url] = self.filepath

    def _get_watermark(self):
        return dedent("""
        * PyWebCopy Engine [version %s]
        * Copyright 2020; Raja Tomar
        * File mirrored from '%s'
        * At UTC datetime: %s
        """) % (__version__, self.response.url, datetime.utcnow())


class HTMLResource(GenericResource):
    def parse(self, **kwargs):
        source, encoding = super(HTMLResource, self).get_source(raw_fp=True)
        return iterparse(source, encoding, collect_ids=False, **kwargs)

    def files(self):
        return (e[2] for e in self.parse())

    def links(self):
        return (e[2] for e in self.parse() if e[0].tag == 'a')

    def extract_children(self, parsing_buffer):
        location = self.filepath

        for elem, attr, url, pos in parsing_buffer:

            if self.invalid_schema(url):
                self.logger.error(
                    "Invalid url schema: [%s] for url: [%s]"
                    % (url.split(':', 1)[0], url)
                )
                continue

            sub_context = self.context.create_new_from_url(url)

            ans = self.scheduler.get_handler(
                elem.tag,
                self.session, self.config, self.scheduler, sub_context
            )
            # self.children.add(ans)
            self.scheduler.handle_resource(ans)
            resolved = ans.resolve(location)
            elem.replace_url(url, resolved, attr, pos)
        return parsing_buffer

    def _retrieve(self):
        if not self.viewing_html():
            self.logger.info("Resource of type [%s] is not HTML." % self.content_type)
            return super(HTMLResource, self)._retrieve()

        if not self.response.ok:
            self.logger.debug("Resource at [%s] is NOT ok and will be NOT processed." % self.url)
            return super(HTMLResource, self)._retrieve()

        parsing_buffer = self.parse()
        rewritten = self.extract_children(parsing_buffer)

        # try:
        #     head = rewritten.root.head
        # except (AttributeError, IndexError):
        #     head = Element('head')
        #     rewritten.root.insert(0, head)
        # #: Write the inferred charset to the html dom so that browsers read this
        # # document in our specified encoding.
        # head.insert(0, Element('meta', charset=self.encoding))

        # WaterMarking :)
        rewritten.root.insert(0, HtmlComment(self._get_watermark()))

        if not os.path.exists(os.path.dirname(self.filepath)):
            os.makedirs(os.path.dirname(self.filepath), mode=0o700)

        # rewritten.root.getroottree().write(self.filepath, method='html')
        retrieve_resource(
            tostring(rewritten.root, include_meta_content_type=True),
            self.filepath, self.context.url, overwrite=True
        )
        self.logger.info('Retrieved content from the url: [%s]' % self.url)
        del parsing_buffer, rewritten
        return self.filepath


class CSSResource(GenericResource):
    def parse(self):
        return self.get_source(raw_fp=False)

    def repl(self, match, encoding=None, fmt=None):
        if fmt is None:
            fmt = "%s"

        url, _ = unquote_match(match.group(1).decode(encoding), match.start(1))
        self.logger.debug("Sub-Css resource found: [%s]" % url)

        if self.invalid_schema(url):
            self.logger.error(
                "Invalid url schema: [%s] for url: [%s]"
                % (url.split(':', 1)[0], url)
            )
            return url.encode(encoding)

        sub_context = self.context.create_new_from_url(url)
        self.logger.debug('Creating context for url: %s as %s' % (url, sub_context))
        ans = self.__class__(
            self.session, self.config, self.scheduler, sub_context
        )
        # self.children.add(ans)
        self.logger.debug("Submitting resource: [%s] to the scheduler." % url)
        self.scheduler.handle_resource(ans)
        re_enc = (fmt % ans.resolve(self.filepath)).encode(encoding)
        self.logger.debug("Re-encoded the resource: [%s] as [%r]" % (url, re_enc))
        return re_enc

    # noinspection PyTypeChecker
    def extract_children(self, parsing_buffer):
        """Schedules the linked files for downloading then resolves their references."""
        source, encoding = parsing_buffer
        source = re.sub(
            (r'url\((' + '["][^"]*["]|' + "['][^']*[']|" + r'[^)]*)\)').encode(encoding),
            partial(self.repl, encoding=encoding, fmt="url('%s')"), source, flags=re.IGNORECASE
        )
        source = re.sub(
            r'@import "(.*?)"'.encode(encoding),
            partial(self.repl, encoding=encoding, fmt='"%s"'), source, flags=re.IGNORECASE
        )
        return BytesIO(source)

    def _retrieve(self):
        """Writes the modified buffer to the disk."""
        if not self.viewing_css():
            self.logger.info("Resource of type [%s] is not CSS." % self.content_type)
            return super(CSSResource, self)._retrieve()

        if not self.response.ok:
            self.logger.debug("Resource at [%s] is NOT ok and will be NOT processed." % self.url)
            return super(CSSResource, self)._retrieve()

        self.logger.debug("Resource at [%s] is ok and will be processed." % self.url)
        retrieve_resource(
            self.extract_children(self.parse()),
            self.filepath, self.url, self.config.get('overwrite')
        )
        self.logger.debug("Finished processing resource [%s]" % self.url)
        return self.filepath


class GenericOnlyResource(GenericResource):
    """Only retrieves a resource if it is not HTML."""

    def _retrieve(self):
        if self.viewing_html():
            self.logger.debug("Resource [%s] is of HTML type and must not be processed!" % self.url)
            return False
        return super(GenericOnlyResource, self)._retrieve()

    def resolve(self, parent_path=None):
        if self.viewing_html():
            return self.context.url
        return super(GenericOnlyResource, self).resolve(parent_path=parent_path)


class VoidResource(GenericResource):
    def get(self, url, **params):
        return None

    def get_source(self, raw_fp=False):
        return None

    def retrieve(self):
        return None


# :)
NullResource = VoidResource


class UrlRemover(VoidResource):
    def resolve(self, parent_path=None):
        return '#'


class AbsoluteUrlResource(VoidResource):
    def resolve(self, parent_path=None):
        return self.context.url


class Base64Resource(GenericResource):
    def resolve(self, parent_path=None):
        source, encoding = self.get_source()
        import sys
        if sys.version > '3':
            if type(source) is bytes:
                return 'data:%s;base64,%s' % (self.content_type, bytes.decode(b64encode(source)))
            else:
                return 'data:%s;base64,%s' % (self.content_type, bytes.decode(b64encode(str.encode(source, encoding))))
        else:
            return 'data:%s;base64,%s' % (self.content_type, b64encode(source))

    def retrieve(self):
        #: There are no sub-files to be fetched.
        return None
