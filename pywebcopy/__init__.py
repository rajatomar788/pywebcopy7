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
import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = ['save_webpage', 'save_website']


def save_webpage(url,
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


# alias for spell check nazi
save_web_page = save_webpage


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
