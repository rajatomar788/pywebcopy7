# Copyright 2020; Raja Tomar
# See license for more details
import errno
import logging
import os
import re
import sys
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
from six import string_types
from six.moves.urllib.request import pathname2url

from .__version__ import __title__
from .__version__ import __version__
from .helpers import cached_property
from .parsers import iterparse
from .parsers import unquote_match
from .urls import get_content_type_from_headers
from .urls import relate

logger = logging.getLogger(__name__)

#: Binary file flags for kernel based io
fd_flags = os.O_CREAT | os.O_WRONLY
if hasattr(os, 'O_BINARY'):
    fd_flags |= os.O_BINARY
if hasattr(os, 'O_NOFOLLOW'):
    fd_flags |= os.O_NOFOLLOW


def make_fd(location, url=None, overwrite=False):
    """Creates a kernel based file descriptor which should be used
    to write binary data onto the files.
    """
    # Sub-directories creation which suppresses exceptions
    base_dir = os.path.dirname(location)
    try:
        os.makedirs(base_dir)
    except (OSError, IOError) as e:
        if e.errno == errno.EEXIST or ((os.name == 'nt' and os.path.isdir(
                base_dir) and os.access(base_dir, os.W_OK))):
            logger.debug(
                "[FILE] Sub-directories exists for: <%r>" % location)
        # dead on arrival
        else:
            logger.error(
                "[File] Failed to create target location <%r> "
                "for the file <%r> on the disk." % (location, url))
            return -1
    else:
        logger.debug(
            "[File] Sub-directories created for: <%r>" % location)
    try:

        sys.audit("%s.resource" % __title__, location)
        if overwrite:
            fd = os.open(location, fd_flags | os.O_TRUNC, 0o600)
        else:
            # raises FileExistsError if file exists
            fd = os.open(location, fd_flags | os.O_EXCL, 0o600)

    except (OSError, PermissionError) as e:
        if e.errno == errno.EEXIST:
            logger.debug(
                "[FILE] <%s> already exists at: <%s>" % (url, location))
        elif e.errno == errno.ENAMETOOLONG:
            logger.debug(
                "[FILE] Path too long for <%s> at: <%s>" % (url, location))
        else:
            logger.error(
                "[File] Cannot write <%s> to <%s>! %r" % (url, location, e))
        return -1
    else:
        return fd


def retrieve_resource(content, location, url=None, overwrite=False):
    """Retrieves the readable resource to a local file.

    ..todo::
        Add overwrite modes: Overwrite or True, Update, Ignore or False

    :param BytesIO content: file like object with read method
    :param location: file name where this content has to be saved.
    :param url: (optional) url of the resource used for logging purposes.
    :param overwrite: (optional) whether to overwrite an existing file.
    :return: rendered location or False if failed.
    """
    assert content is not None, "Content can't be of NoneType."
    assert location is not None, "Context can't be of NoneType."
    assert url is not None, "Url can't be of NoneType."

    logger.debug(
        "[File] Preparing to write file from <%r> to the disk at <%r>."
        % (url, location))

    fd = make_fd(location, url, overwrite)
    if fd == -1:
        return location

    with closing(os.fdopen(fd, 'w+b')) as dst:
        copyfileobj(content, dst)

    logger.info(
        "[File] Written the file from <%s> to <%s>" % (url, location))
    return location


def urlretrieve(url, location, **params):
    """
    A extra rewrite of a basic `urllib` function using the
    tweaks and perks of this library.

    :param url: url of the resource to be retrieved.
    :param location: destination for the resource.
    :params \*\*params: parameters for the :func:`requests.get`.
    :return: location of the file retrieved.
    """
    if not isinstance(url, string_types):
        raise TypeError("Expected string type, got %r" % url)
    if not isinstance(location, string_types):
        raise TypeError("Expected string type, got %r" % location)

    import requests
    with closing(requests.get(url, **params)) as src:
        return retrieve_resource(
            src.raw, location, url, overwrite=True)


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
        """Update the response attribute of this object.

        It also updates the content_type and encoding as reported by the
        server implicitly for better detection of contents."""
        self.response = response
        self.__dict__.pop('url', None)
        self.__dict__.pop('filepath', None)
        self.__dict__.pop('filename', None)
        if response.ok:
            #: Clear the cached properties
            self.__dict__.pop('content_type', None)
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
        return ''

    @cached_property
    def url(self):
        if self.response is not None:
            self.context = self.context.with_values(url=self.response.url)
        return self.context.url

    @cached_property
    def encoding(self):
        if self.response is not None:
            #: Explicit encoding takes precedence
            return self.config.get(
                'encoding', self.response.encoding or 'ascii')
        return self.config.get('encoding', 'ascii')

    html_content_types = tuple([
        'text/htm',
        'text/html',
        'text/xhtml'
    ])

    def viewing_html(self):
        return self.content_type in self.html_content_types

    css_content_types = tuple([
        'text/css',
    ])

    def viewing_css(self):
        return self.content_type in self.css_content_types

    js_content_types = tuple([
        'text/javascript',
        'application/javascript'
    ])

    def viewing_js(self):
        return self.content_type in self.js_content_types

    def request(self, method, url, **params):
        """Fetches the Html content from Internet using the requests.
        You can any requests params which will be passed to the library
        itself.
        The requests arguments you supply will also be applied to the
        global session meaning all the files will be downloaded using these
        settings.

        :param method: http verb for transport.
        :param url: url of the page to fetch
        :param params: keyword arguments which `requests` module may accept.
        """
        if params.pop('stream', None):
            warnings.warn(UserWarning(
                "Stream attribute is True by default for reasons."
            ))
        self.set_response(
            self.session.request(method, url, stream=True, **params))

    def get(self, url, **params):
        return self.request('GET', url, **params)

    def post(self, url, **params):
        return self.request('POST', url, **params)

    def resolve(self, parent_path=None):
        """Calculates the location at which this response should be stored as a file."""
        filepath = self.filepath
        if not isinstance(filepath, string_types):
            raise ValueError("Invalid filepath [%r]" % filepath)
        if parent_path and isinstance(parent_path, string_types):
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
                self.response = self.session.get(self.url)
            self.response.raw.decode_content = True
            return self.response.raw, self.encoding
        return self.response.content, self.encoding

    def retrieve(self):
        """Retrieves the readable resource to the local disk."""
        if self.response is None:
            raise AttributeError(
                "Response attribute is not set!"
                "You need to fetch the resource using get method!"
            )
        # XXX: Validate resource here?
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
                self.logger.error(
                    "Response object for url <%s> has no attribute 'raw'!" % self.url)
                content = BytesIO(self.response.content)
            else:
                content = self.response.raw

        retrieve_resource(
            content, self.filepath, self.context.url, self.config.get('overwrite'))
        del content
        return self.filepath


class HTMLResource(GenericResource):
    """Interpreter for resource written in or reported as html."""
    def parse(self, **kwargs):
        source, encoding = super(HTMLResource, self).get_source(raw_fp=True)
        return iterparse(
            source, encoding, include_meta_charset_tag=True, **kwargs)

    def extract_children(self, parsing_buffer):
        location = self.filepath

        for elem, attr, url, pos in parsing_buffer:
            if not self.scheduler.validate_url(url):
                continue

            sub_context = self.context.create_new_from_url(url)
            ans = self.scheduler.get_handler(
                elem.tag,
                self.session, self.config, self.scheduler, sub_context)
            self.scheduler.handle_resource(ans)
            resolved = ans.resolve(location)
            elem.replace_url(url, resolved, attr, pos)

        return parsing_buffer

    def _retrieve(self):
        if not self.viewing_html():
            self.logger.info(
                "Resource of type [%s] is not HTML." % self.content_type)
            return super(HTMLResource, self)._retrieve()

        if not self.response.ok:
            self.logger.debug(
                "Resource at [%s] is NOT ok and will be NOT processed." % self.url)
            return super(HTMLResource, self)._retrieve()

        parsing_buffer = self.parse()
        context = self.extract_children(parsing_buffer)

        # WaterMarking :)
        context.root.insert(0, HtmlComment(self._get_watermark()))

        retrieve_resource(
            BytesIO(tostring(context.root, include_meta_content_type=True)),
            self.filepath, self.context.url, overwrite=True)

        self.logger.debug('Retrieved content from the url: [%s]' % self.url)
        del parsing_buffer, context
        return self.filepath

    def _get_watermark(self):
        # comment text should be in unicode
        return dedent("""
        * PyWebCopy Engine [version %s]
        * Copyright 2020; Raja Tomar
        * File mirrored from [%s]
        * At UTC datetime: [%s]
        """) % (__version__, self.response.url, datetime.utcnow())


class CSSResource(GenericResource):
    def parse(self):
        return self.get_source(raw_fp=False)

    def repl(self, match, encoding=None, fmt=None):
        fmt = fmt or '%s'

        url, _ = unquote_match(match.group(1).decode(encoding), match.start(1))
        self.logger.debug("Sub-Css resource found: [%s]" % url)

        if not self.scheduler.validate_url(url):
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


class JSResource(GenericResource):
    def parse(self):
        return self.get_source(raw_fp=False)

    def repl(self, match, encoding=None):
        url, _ = unquote_match(match.group(1).decode(encoding), match.start(1))
        self.logger.debug("Sub-JS resource found: [%s]" % url)

        if not self.scheduler.validate_url(url):
            return url.encode(encoding)

        sub_context = self.context.create_new_from_url(url)
        self.logger.debug('Creating context for url: %s as %s' % (url, sub_context))
        ans = self.__class__(
            self.session, self.config, self.scheduler, sub_context
        )
        # self.children.add(ans)
        self.logger.debug("Submitting resource: [%s] to the scheduler." % url)
        self.scheduler.handle_resource(ans)
        re_enc = (ans.resolve(self.filepath)).encode(encoding)
        self.logger.debug("Re-encoded the resource: [%s] as [%r]" % (url, re_enc))
        return re_enc

    # noinspection PyTypeChecker
    def extract_children(self, parsing_buffer):
        """Schedules the linked files for downloading then resolves their references."""
        source, encoding = parsing_buffer
        # P.S. Regex is from this github repo under MIT license
        # https://github.com/GerbenJavado/LinkFinder/
        source = re.sub(
            (r"""
            (?:"|')                               # Start newline delimiter
            (
                ((?:[a-zA-Z]{1,10}://|//)           # Match a scheme [a-Z]*1-10 or //
                [^"'/]{1,}\.                        # Match a domain-name (any character + dot)
                [a-zA-Z]{2,}[^"']{0,})              # The domain-extension and/or path
                |
                ((?:/|\.\./|\./)                    # Start with /,../,./
                [^"'><,;| *()(%%$^/\\\[\]]          # Next character can't be...
                [^"'><,;|()]{1,})                   # Rest of the characters can't be
                |
                ([a-zA-Z0-9_\-/]{1,}/               # Relative endpoint with /
                [a-zA-Z0-9_\-/]{1,}                 # Resource name
                \.(?:[a-zA-Z]{1,4}|action)          # Rest + extension (length 1-4 or action)
                (?:[\?|#][^"|']{0,}|))              # ? or # mark with parameters
                |
                ([a-zA-Z0-9_\-/]{1,}/               # REST API (no extension) with /
                [a-zA-Z0-9_\-/]{3,}                 # Proper REST endpoints usually have 3+ chars
                (?:[\?|#][^"|']{0,}|))              # ? or # mark with parameters
                |
                ([a-zA-Z0-9_\-]{1,}                 # filename
                \.(?:php|asp|aspx|jsp|json|
                     action|html|js|txt|xml)        # . + extension
                (?:[\?|#][^"|']{0,}|))              # ? or # mark with parameters
            )
            (?:"|')                               # End newline delimiter
            """).encode(encoding),
            partial(self.repl, encoding=encoding), source, flags=re.IGNORECASE
        )
        return BytesIO(source)

    def _retrieve(self):
        """Writes the modified buffer to the disk."""
        if not self.viewing_js():
            self.logger.info("Resource of type [%s] is not JS." % self.content_type)
            return super(JSResource, self)._retrieve()

        if not self.response.ok:
            self.logger.debug("Resource at [%s] is NOT ok and will be NOT processed." % self.url)
            return super(JSResource, self)._retrieve()

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
