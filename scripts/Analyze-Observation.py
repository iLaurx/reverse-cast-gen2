"""Resume observaciones ya guardadas sin conectar al dispositivo."""
import argparse
import collections
import json
import pathlib


def summarize(path):
    events = []
    incomplete_last_line = False
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            incomplete_last_line = True
    counts = collections.Counter(e['kind'] for e in events)
    transitions, previous = [], object()
    uptime, drops, media, contents = [], [], [], set()
    for event in events:
        if event['kind'] == 'receiver':
            current = (event.get('app_id'), event.get('session_ref'))
            if current != previous:
                transitions.append({k: event.get(k) for k in (
                    'time_utc', 'elapsed_s', 'app_id', 'app_name', 'session_ref', 'namespaces')})
                previous = current
        if event['kind'] == 'device' and isinstance(event.get('uptime'), (int, float)):
            if uptime and event['uptime'] < uptime[-1]['uptime']:
                drops.append({'before': uptime[-1], 'after': event})
            uptime.append(event)
        if event['kind'] == 'media':
            media.append(event)
            content = event.get('content') or {}
            if content.get('youtube_video_id_candidate'):
                contents.add(content['youtube_video_id_candidate'])
    return {'source': str(path), 'event_count': len(events), 'counts': dict(counts),
            'window_start': events[0]['time_utc'] if events else None,
            'window_end': events[-1]['time_utc'] if events else None,
            'completed': bool(counts.get('end')), 'invalid_lines_present': incomplete_last_line,
            'application_transitions': transitions,
            'connection_events': [e for e in events if e['kind'] == 'connection'],
            'uptime_samples': len(uptime), 'uptime_decreases': drops,
            'media_states': dict(collections.Counter(e.get('playerState') for e in media)),
            'idle_reasons': dict(collections.Counter(str(e.get('idleReason')) for e in media)),
            'ad_break_observations': sum(e.get('ad_break') is not None for e in media),
            'youtube_id_candidates': sorted(contents),
            'last_media_observation': media[-1] if media else None}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=pathlib.Path)
    parser.add_argument('--output', type=pathlib.Path)
    args = parser.parse_args()
    text = json.dumps(summarize(args.path), indent=2, ensure_ascii=False)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(text + '\n')
    print(text)
