import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import httpx
from providers import Providers
from transit_speech import transit_speech

class TransitSpeechTests(unittest.TestCase):
    def test_future_departure_comes_from_returned_timestamp(self):
        route = {'line': '5', 'stop': 'Market Street', 'departure_time': '2026-11-14T22:05:01Z'}
        spoken = transit_speech(route, datetime(2026,11,14,22,0,tzinfo=timezone.utc))
        self.assertIn('6 minutes', spoken)
        self.assertIn('estimated', spoken)

    def test_expired_estimate_is_not_called_the_next_bus(self):
        spoken = transit_speech({'line': '5', 'stop': 'Market', 'departure_time': '2026-11-14T21:00:00Z'},
                                datetime(2026,11,14,22,0,tzinfo=timezone.utc))
        self.assertIn('already passed', spoken)

class ProviderConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_low_is_sent_to_gemini(self):
        def respond(request):
            data = json.loads(request.content)
            self.assertEqual(data['generationConfig']['thinkingConfig']['thinkingLevel'], 'LOW')
            return httpx.Response(200, json={'candidates':[{'content':{'parts':[{'text':'{"ok":true}'}]}}]})
        with patch.dict(os.environ, {'GEMINI_API_KEY':'fixture', 'GEMINI_THINKING_LEVEL':'LOW'}):
            provider = Providers()
            await provider.http.aclose()
            provider.http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
            try:
                self.assertTrue((await provider.gemini('test', {'type':'OBJECT'}))['ok'])
            finally: await provider.close()

    async def test_bus_timing_and_food_requests_route_without_model_wait(self):
        provider = Providers()
        try:
            self.assertEqual((await provider.plan('When is the next bus coming?'))['scene'], 'bus_timing')
            self.assertEqual((await provider.plan('Where is the food in this room?'))['scene'], 'shelf')
        finally: await provider.close()

if __name__ == '__main__': unittest.main()
