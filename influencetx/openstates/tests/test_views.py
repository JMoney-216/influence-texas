from contextlib import contextmanager
from unittest import mock

from django.core.exceptions import ImproperlyConfigured
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import reverse
from django.test import SimpleTestCase
from faker import Factory

from influencetx.openstates import views
from influencetx.testing.view_utils import render_view, response_from_view


FAKE = Factory.create()


def test_index_view():
    html = render_view('openstates:index')
    assert reverse('openstates:legislator-list') in html
    assert reverse('openstates:bill-list') in html


def test_api_key_required_view():
    html = render_view('openstates:api-key-required')
    assert 'https://openstates.org/api/register/' in html


class BaseOpenStatesAPITestCase(SimpleTestCase):

    def assert_redirect_when_debugging(self, view_name, args=None, kwargs=None):
        """Assert view redirects to error page when api-key is missing and in debug mode."""
        with mock_fetch_with_no_api_key(), use_debug_mode(True):
            response = response_from_view(view_name, args=args, kwargs=kwargs)
            self.assertRedirects(response, reverse('openstates:api-key-required'))

    def assert_raises_when_not_debugging(self, view_name, args=None, kwargs=None):
        """Assert view raises error when api-key is missing and in debug mode."""
        with mock_fetch_with_no_api_key(), use_debug_mode(False):
            with self.assertRaises(ImproperlyConfigured):
                response_from_view(view_name, args=args, kwargs=kwargs)


class TestLegislatorListView(BaseOpenStatesAPITestCase):

    def test_no_api_key(self):
        self.assert_redirect_when_debugging('openstates:legislator-list')
        self.assert_raises_when_not_debugging('openstates:legislator-list')

    def test_data_rendering(self):
        legislator = fake_legislator()
        detail_url = reverse('openstates:legislator-detail', args=(legislator['leg_id'],))

        with mock_fetch() as fetch:
            fetch.legislators.return_value = [legislator]
            html = render_view('openstates:legislator-list')

        assert detail_url in html
        for value in legislator.values():
            assert value in html


class TestLegislatorDetailView(BaseOpenStatesAPITestCase):

    def test_no_api_key(self):
        args = (FAKE.pyint(), FAKE.pystr())
        self.assert_redirect_when_debugging('openstates:bill-detail', args=args)
        self.assert_raises_when_not_debugging('openstates:bill-detail', args=args)

    def test_data_rendering(self):
        legislator = fake_legislator()
        leg_id = legislator['leg_id']

        with mock_fetch() as fetch:
            fetch.legislators.return_value = legislator
            html = render_view('openstates:legislator-detail', args=(leg_id,))

        fetch.legislators.assert_called_once_with(leg_id)
        assert legislator['full_name'] in html
        assert legislator['district'] in html
        assert legislator['party'] in html
        assert legislator['chamber'] in html

    def test_legislator_not_found(self):
        with mock_fetch() as fetch:
            fetch.legislators.return_value = None
            with self.assertRaises(Http404):
                render_view('openstates:legislator-detail', kwargs={'leg_id': FAKE.pystr()})


class TestBillListView(BaseOpenStatesAPITestCase):

    def test_no_api_key(self):
        self.assert_redirect_when_debugging('openstates:bill-list')
        self.assert_raises_when_not_debugging('openstates:bill-list')

    def test_data_rendering(self):
        bill = {
            'bill_id': FAKE.pystr(),
            'title': FAKE.pystr(),
            'subjects': FAKE.pystr(),
            'session': str(FAKE.pyint()),
        }
        detail_url = reverse('openstates:bill-detail', args=(bill['session'], bill['bill_id']))

        with mock_fetch() as fetch:
            fetch.bills.return_value = [bill]
            html = render_view('openstates:bill-list')

        assert detail_url in html
        for key, value in bill.items():
            assert value in html



class TestBillDetailView(BaseOpenStatesAPITestCase):

    def test_no_api_key(self):
        args = (FAKE.pyint(), FAKE.pystr())
        self.assert_redirect_when_debugging('openstates:bill-detail', args=args)
        self.assert_raises_when_not_debugging('openstates:bill-detail', args=args)

    def test_data_rendering(self):
        bill_id = FAKE.pystr()
        session = FAKE.pyint()
        bill = {
            'bill_id': bill_id,
            'title': FAKE.pystr(),
            'subjects': [FAKE.pystr()],
            'session': session,
            'action_dates': {
                FAKE.pystr(): fake_openstates_timestamp(),
            },
            'votes': [{
                'date': fake_openstates_timestamp(),
                'yes_count': FAKE.pyint(),
                'no_count': FAKE.pyint(),
                'chamber': FAKE.pystr(),
            }],
        }

        with mock_fetch() as fetch:
            fetch.bill_detail.return_value = bill
            html = render_view('openstates:bill-detail',
                                       kwargs={'session': session, 'id': bill_id})

        fetch.bill_detail.assert_called_once_with(session=session, pk=bill_id)

        assert bill_id in html
        assert bill['title'] in html
        assert bill['subjects'][0] in html
        assert str(session) in html

        action, date = list(bill['action_dates'].items())[0]
        date, timestamp = date.split()
        assert action in html
        assert date in html
        assert timestamp not in html

        vote = bill['votes'][0]
        date, timestamp = vote['date'].split()
        assert date in html
        assert timestamp not in html
        assert str(vote['yes_count']) in html
        assert str(vote['no_count']) in html
        assert vote['chamber'] in html

    def test_bill_not_found(self):
        bill_kwargs = {'session': FAKE.pyint(), 'id': FAKE.pystr()}
        with mock_fetch() as fetch:
            fetch.bill_detail.return_value = None
            with self.assertRaises(Http404):
                render_view('openstates:bill-detail', kwargs=bill_kwargs)


@contextmanager
def mock_fetch():
    with mock.patch.object(views, 'fetch') as fetch:
        yield fetch

@contextmanager
def mock_fetch_with_no_api_key():
    with mock_fetch() as fetch:
        fetch.OPENSTATES_API_KEY = None
        yield fetch


@contextmanager
def use_debug_mode(is_debug):
    with mock.patch.object(views, 'settings') as settings:
        settings.DEBUG = is_debug
        yield


def fake_legislator():
    legislator = {
        'leg_id': FAKE.pystr(),
        'full_name': FAKE.name(),
        'district': FAKE.pystr(),
        'party': FAKE.pystr(),
        'chamber': FAKE.pystr(),
    }
    return legislator


def fake_openstates_timestamp():
    """Return fake timestamp matching Open States' formatting."""
    return FAKE.iso8601().replace('T', ' ')
