# Copyright (C) 2019  The Software Heritage developers
# See the AUTHORS file at the top-level directory of this distribution
# License: GNU General Public License version 3, or any later version
# See top-level LICENSE file for more information

"""Wrapper around requests-mock to mock successive responses
from a web service.

Tests can build successive steps by calling :py:meth:`WebScenario.add_step`
with specifications of what endpoints should be called and in what order."""

from dataclasses import dataclass
import json
from typing import Callable, List, Optional, Set

import requests_mock


@dataclass(frozen=True)
class Step:
    expected_method: str
    expected_url: str
    response: object
    status_code: int = 200
    callback: Optional[Callable[[], int]] = None


@dataclass(frozen=True)
class Endpoint:
    method: str
    url: str


class WebScenario:
    """Stores the state of the successive calls to the web service
    expected by tests."""

    _steps: List[Step]
    _endpoints: Set[Endpoint]
    _current_step: int

    def __init__(self):
        self._steps = []
        self._endpoints = set()
        self._current_step = 0

    def add_endpoint(self, *args, **kwargs):
        """Adds an endpoint to be mocked.

        Arguments are the same as :py:class:Endpoint.
        """
        self._endpoints.add(Endpoint(*args, **kwargs))

    def add_step(self, *args, **kwargs):
        """Adds an expected call to the list of expected calls.
        Also automatically calls :py:meth:`add_endpoint` so the
        associated endpoint is mocked.

        Arguments are the same as :py:class:`Step`.
        """
        step = Step(*args, **kwargs)
        self._steps.append(step)
        self.add_endpoint(step.expected_method, step.expected_url)

    def install_mock(self, mocker: requests_mock.Mocker):
        """Mocks entrypoints registered with :py:meth:`add_endpoint`
        (or :py:meth:`add_step`) using the provided mocker.
        """
        for endpoint in self._endpoints:
            mocker.register_uri(
                endpoint.method.upper(), endpoint.url, text=self._request_callback
            )

    def _request_callback(self, request, context):
        step = self._steps[self._current_step]

        assert request.url == step.expected_url
        assert request.method.upper() == step.expected_method.upper()

        self._current_step += 1

        context.status_code = step.status_code

        if step.callback:
            step.callback()

        if isinstance(step.response, str):
            return step.response
        else:
            return json.dumps(step.response)
