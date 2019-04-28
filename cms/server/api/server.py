#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2017 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2016 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
# Copyright © 2017 Kiarash Golezardi <kiarashgolezardi@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Web server for the API.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import base64
import logging
import pkg_resources

from cms import ConfigError, ServiceCoord, config
from cms.io import WebService
from cms.db.filecacher import FileCacher

from .handlers import HANDLERS


logger = logging.getLogger(__name__)


class APIWebServer(WebService):
    """Service that runs the web server for the API.

    """
    def __init__(self, shard):
        parameters = {
            "login_url": "/",
            "template_path": pkg_resources.resource_filename(
                "cms.server.api", "templates"),
            "static_files": [],
            "cookie_secret": base64.b64encode(config.secret_key),
            "debug": config.tornado_debug,
            "is_proxy_used": config.is_proxy_used,
            "num_proxies_used": config.num_proxies_used,
            "xsrf_cookies": False,
        }
        super(APIWebServer, self).__init__(
            config.api_listen_port,
            HANDLERS,
            parameters,
            shard=shard,
            listen_address=config.api_listen_address)

        self.contest = None

        self.file_cacher = FileCacher(self)
        self.evaluation_service = self.connect_to(
            ServiceCoord("EvaluationService", 0))
