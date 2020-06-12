"""
    ____       _       __     __    ______
   / __ \__  _| |     / /__  / /_  / ____/___  ____  __  __
  / /_/ / / / / | /| / / _ \/ __ \/ /   / __ \/ __ \/ / / /
 / ____/ /_/ /| |/ |/ /  __/ /_/ / /___/ /_/ / /_/ / /_/ /
/_/    \__, / |__/|__/\___/_.___/\____/\____/ .___/\__, /
      /____/                               /_/    /____/

PyWebCopy is a free tool for copying full or partial websites locally
onto your hard-disk for offline viewing.

PyWebCopy will scan the specified website and download its content onto your hard-disk.
Links to resources such as style-sheets, images, and other pages in the website
will automatically be remapped to match the local path.
Using its extensive configuration you can define which parts of a website will be copied and how.

What can PyWebCopy do?
PyWebCopy will examine the HTML mark-up of a website and attempt to discover all linked resources
such as other pages, images, videos, file downloads - anything and everything.
It will download all of theses resources, and continue to search for more.
In this manner, WebCopy can "crawl" an entire website and download everything it sees
in an effort to create a reasonable facsimile of the source website.

What can PyWebCopy not do?
PyWebCopy does not include a virtual DOM or any form of JavaScript parsing.
If a website makes heavy use of JavaScript to operate, it is unlikely PyWebCopy will be able
to make a true copy if it is unable to discover all of the website due to
JavaScript being used to dynamically generate links.

PyWebCopy does not download the raw source code of a web site,
it can only download what the HTTP server returns.
While it will do its best to create an offline copy of a website,
advanced data driven websites may not work as expected once they have been copied.


# Copyright 2020; Raja Tomar
# See license for more details
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""

import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ['save_page', 'save_website', 'save_webpage']


def save_page(url,
              project_folder=None,
              project_name=None,
              bypass_robots=None,
              debug=False,
              open_in_browser=True,
              delay=None):
    from .configs import get_config
    config = get_config(url, project_folder, project_name, bypass_robots, debug, delay)
    page = config.create_page()
    page.get(url)
    page.save_complete(pop=open_in_browser)


save_web_page = save_webpage = save_page


def save_website(url,
                 project_folder=None,
                 project_name=None,
                 bypass_robots=None,
                 debug=False,
                 open_in_browser=False,
                 delay=None):
    from .configs import get_config
    config = get_config(url, project_folder, project_name, bypass_robots, debug, delay)
    crawler = config.create_crawler()
    crawler.get(url)
    crawler.save_complete(pop=open_in_browser)
