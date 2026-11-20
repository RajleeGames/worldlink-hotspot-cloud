"""Probe the single approved Omada AP using a view-only Open API credential."""

import time

from django.core.management.base import BaseCommand, CommandError

from networks.omada_monitor import OmadaMonitorError, poll_approved_pilot


class Command(BaseCommand):
    help = 'Read-only Omada AP status for the already-approved Eaglelink pilot (no Wi-Fi writes).'

    def add_arguments(self, parser):
        parser.add_argument('--loop', action='store_true', help='Poll repeatedly for a dedicated service.')
        parser.add_argument('--interval', type=int, default=30, help='Seconds between probes (15–300).')

    def handle(self, *args, **options):
        interval = options['interval']
        if interval < 15 or interval > 300:
            raise CommandError('Choose a polling interval between 15 and 300 seconds.')
        while True:
            try:
                observation = poll_approved_pilot()
                self.stdout.write(f'Omada AP #{observation.router_id}: {observation.get_state_display()} '
                                  f'(checked {observation.checked_at:%Y-%m-%d %H:%M:%S} UTC).')
            except OmadaMonitorError as exc:
                if not options['loop']:
                    raise CommandError(str(exc)) from exc
                self.stderr.write(f'Omada status probe: {exc}')
            if not options['loop']:
                return
            time.sleep(interval)
