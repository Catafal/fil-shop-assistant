"""Versioned isolated audio trials. Provider generate/run requires explicit authorization."""
import argparse
import asyncio
import base64
import json
import os
import re
import sqlite3
import time
import wave
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedOK

from fil_shop.audio_evaluation import (
    HARNESS_VERSION,
    AudioTrace,
    business_state_grade,
    digest,
    file_digest,
    load_case,
    provider_digest,
    read_outcome,
    spoken_grade,
    trial_validity,
    validate_case_clock,
    validate_target,
)


class ProviderEnded(Exception):
    """Normal provider termination; completeness is decided from the observed trace."""


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def wav(path, data, rate):
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(data)


def generate(client, root, case):
    root.mkdir(parents=True, exist_ok=False)
    state = {'schema': 2, 'synthetic_caller': True, 'case': case, 'case_sha256': digest(case),
             'generator': {'voice_id': 'wwjcRqvD8HTFsOs1fkFm', 'model': 'eleven_v4_turbo',
                           'format': 'pcm_16000'}, 'fixtures': []}
    manifest = root / 'fixtures.json'
    save(manifest, state)
    for index, turn in enumerate(case['turns']):
        state['pending'] = {'generate': turn['id']}
        save(manifest, state)
        pcm = b''.join(client.text_to_speech.convert(
            state['generator']['voice_id'], text=turn['text'], model_id='eleven_v4_turbo',
            language_code=turn['language'], output_format='pcm_16000',
            request_options={'max_retries': 0},
        ))
        if not pcm or len(pcm) % 2 or len(pcm) > 32000 * 30:
            raise ValueError('Invalid or unexpectedly long caller audio')
        name = f'caller-{index}.wav'
        wav(root / name, pcm, 16000)
        state['fixtures'].append({'turn_id': turn['id'], 'file': name,
                                  'sha256': file_digest(root / name), 'seconds': len(pcm) / 32000})
        state.pop('pending')
        save(manifest, state)
    print(f"Generated {len(state['fixtures'])} versioned synthetic caller fixtures")


def load_fixtures(root, case):
    fixtures = json.loads((root / 'fixtures.json').read_text())
    if (fixtures.get('schema') != 2 or fixtures.get('pending')
            or fixtures.get('case_sha256') != digest(case) or fixtures.get('case') != case
            or [f.get('turn_id') for f in fixtures.get('fixtures', [])] != [t['id'] for t in case['turns']]):
        raise ValueError('Fixture case/version differs or generation is incomplete')
    for item in fixtures['fixtures']:
        path = root / item['file']
        if path.is_symlink() or path.parent.resolve() != root.resolve() or file_digest(path) != item['sha256']:
            raise ValueError('Caller audio artifact changed or escapes fixture directory')
    return fixtures


def verify_provider(client, provision, agent_id):
    snapshot = client.conversational_ai.agents.get(agent_id).model_dump(exclude_none=True)
    if provider_digest(snapshot, 'agent') != provision['agent_snapshot_sha256']:
        raise ValueError('Evaluation agent differs from provisioned candidate')
    seen = set(snapshot.get('conversation_config', {}).get('agent', {}).get('prompt', {}).get('tool_ids', []))
    for node in snapshot.get('workflow', {}).get('nodes', {}).values():
        seen.update(node.get('additional_tool_ids', []))
    if seen != set(provision['tool_ids'].values()):
        raise ValueError('Agent does not expose exactly the provisioned evaluation tools')
    for name, tool_id in provision['tool_ids'].items():
        tool = client.conversational_ai.tools.get(tool_id).model_dump(exclude_none=True)
        if provider_digest(tool, 'tool') != provision['tool_snapshot_sha256'][name]:
            raise ValueError('Evaluation tool differs from provisioned snapshot')
    return snapshot


def safe_close_reason(value):
    # Never copy URLs/capabilities or long credential-like strings from network exceptions.
    text = re.sub(r'https?://\S+|wss?://\S+|[A-Za-z0-9_-]{32,}', '[redacted]', str(value))
    return text[:240]


async def run(client, root, case, agent_id, evaluation_root, provision_path, trial_id):
    provision = json.loads(provision_path.read_text())
    evaluation_root = validate_target(provision, agent_id, evaluation_root,
                                      os.environ.get('ELEVENLABS_AGENT_ID'))
    fixtures = load_fixtures(root, case)
    verify_provider(client, provision, agent_id)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', trial_id):
        raise ValueError('Explicit bounded trial ID required')
    trial_root = root / 'trials' / trial_id
    trial_root.mkdir(parents=True, exist_ok=False)
    output = trial_root / 'audio-run.json'
    state = {'schema': 2, 'harness_version': HARNESS_VERSION, 'trial_id': trial_id,
             'case_id': case['id'], 'case_version': case['version'], 'case_sha256': digest(case),
             'fixture_sha256': file_digest(root / 'fixtures.json'),
             'provision_sha256': file_digest(provision_path), 'candidate_sha256': provision['agent_snapshot_sha256'],
             'synthetic_caller': True, 'agent_id': agent_id, 'events': [], 'sent': [],
             'pending': 'signed_url', 'browser_webrtc_tested': False,
             'physical_playback_observed': False, 'received_audio_is_wallclock_recording': False}
    save(output, state)
    signed = client.conversational_ai.conversations.get_signed_url(
        agent_id=agent_id, request_options={'max_retries': 0},
    ).signed_url
    started = time.monotonic()
    trace = AudioTrace()
    metadata = asyncio.Event()
    audio = bytearray()
    audio_rate = 0
    all_sent = False
    state['pending'] = 'connect'
    save(output, state)

    def elapsed():
        return time.monotonic() - started

    def checkpoint():
        state['events'] = trace.events
        save(output, state)

    def observe(kind, **data):
        event = trace.observe(kind, elapsed(), **data)
        checkpoint()
        return event

    try:
        async with connect(signed, max_size=8 * 1024 * 1024, open_timeout=20) as socket:
            await socket.send(json.dumps({'type': 'conversation_initiation_client_data'}))

            async def receive():
                nonlocal audio_rate
                try:
                    async for raw in socket:
                        event = json.loads(raw)
                        kind = event.get('type')
                        if kind == 'ping':
                            await socket.send(json.dumps({'type': 'pong', 'event_id': event['ping_event']['event_id']}))
                        elif kind == 'conversation_initiation_metadata':
                            info = event['conversation_initiation_metadata_event']
                            if info['user_input_audio_format'] != 'pcm_16000':
                                raise ValueError('Unsupported negotiated input format')
                            fmt = info['agent_output_audio_format']
                            if fmt not in ('pcm_16000', 'pcm_22050', 'pcm_24000', 'pcm_44100', 'pcm_48000'):
                                raise ValueError('Unsupported negotiated output format')
                            audio_rate = int(fmt.split('_')[1])
                            state.update({'conversation_id': info['conversation_id'], 'input_format': 'pcm_16000', 'output_format': fmt})
                            state.pop('pending', None)
                            observe(kind)
                            metadata.set()
                        elif kind == 'audio':
                            chunk = base64.b64decode(event['audio_event']['audio_base_64'], validate=True)
                            item = observe('audio', bytes=len(chunk), rate=audio_rate,
                                           event_id=int(event['audio_event']['event_id']),
                                           response_id=event['audio_event'].get('response_id'))
                            if not item['discarded']:
                                audio.extend(chunk)
                        elif kind == 'agent_response':
                            observe(kind, text=event['agent_response_event']['agent_response'],
                                    event_id=event['agent_response_event'].get('event_id'),
                                    response_id=event['agent_response_event'].get('response_id'))
                        elif kind == 'user_transcript':
                            observe(kind, text=event['user_transcription_event']['user_transcript'])
                        elif kind == 'interruption':
                            observe(kind, event_id=int(event['interruption_event']['event_id']))
                        elif kind == 'agent_response_complete':
                            observe(kind)
                        elif kind == 'agent_tool_response':
                            info = event.get('agent_tool_response', event.get('agent_tool_response_event', {}))
                            observe('tool_error' if info.get('is_error') else 'tool_result',
                                    tool_name=info.get('tool_name'), code='provider_tool_error' if info.get('is_error') else None)
                        elif kind in {'error', 'client_error'}:
                            observe('provider_error', code=kind)
                except ConnectionClosedOK:
                    pass
                except Exception as error:  # noqa: BLE001 - sanitize network/provider failures
                    observe('provider_error', code=type(error).__name__)
                finally:
                    observe('provider_end', code=socket.close_code,
                            reason=safe_close_reason(socket.close_reason or 'no_reason'))
                    metadata.set()

            receiver = asyncio.create_task(receive())
            try:
                await asyncio.wait_for(metadata.wait(), 20)
                if not state.get('conversation_id'):
                    raise ProviderEnded('Provider ended before metadata')

                async def tick():
                    if elapsed() > case['max_seconds']:
                        observe('timeout', code='call_duration_cap')
                        raise TimeoutError('Audio call duration cap')
                    if receiver.done():
                        # Still allow already-received final audio to virtually drain; never
                        # invent a final response merely because the provider closed normally.
                        await asyncio.sleep(.1)
                        return
                    try:
                        await socket.send(json.dumps({'user_audio_chunk': base64.b64encode(bytes(3200)).decode()}))
                    except ConnectionClosedOK:
                        # A normal close can race the open-microphone silence send. Drain
                        # queued receiver events before deciding whether a farewell exists.
                        await receiver
                    await asyncio.sleep(.1)

                for index, (turn, fixture) in enumerate(zip(case['turns'], fixtures['fixtures'])):
                    wait_start = elapsed()
                    while True:
                        now = elapsed()
                        if index == 0 and trace.greeting_ready(now):
                            break
                        if index and turn['send_mode'] == 'overlap' and trace.response_ordered() and trace.playback_until > now + .5:
                            observe('overlap_attempt', id=turn['id'], kind_label=turn['kind'])
                            break
                        if index and turn['send_mode'] == 'after_response' and trace.drained(now):
                            break
                        if trace.end:
                            raise ProviderEnded('Provider ended before next caller turn')
                        if now - wait_start > 45:
                            observe('timeout', code='previous_response_absent')
                            raise TimeoutError('No completed previous response')
                        await tick()
                    observe('input_start', id=turn['id'], kind_label=turn['kind'], send_mode=turn['send_mode'])
                    state['sent'].append({'id': turn['id'], 'text': turn['text'], 'at': elapsed()})
                    checkpoint()
                    with wave.open(str(root / fixture['file']), 'rb') as stream:
                        if stream.getframerate() != 16000 or stream.getnchannels() != 1 or stream.getsampwidth() != 2:
                            raise ValueError('Caller WAV contract mismatch')
                        pcm = stream.readframes(stream.getnframes())
                    for offset in range(0, len(pcm), 3200):
                        if elapsed() > case['max_seconds']:
                            observe('timeout', code='call_duration_cap')
                            raise TimeoutError('Audio duration cap')
                        try:
                            await socket.send(json.dumps({'user_audio_chunk': base64.b64encode(pcm[offset:offset + 3200]).decode()}))
                        except ConnectionClosedOK:
                            await receiver
                            raise ProviderEnded('Provider ended during caller audio') from None
                        await asyncio.sleep(.1)
                    observe('input_end', id=turn['id'])
                    all_sent = index == len(case['turns']) - 1
                    wait_start = elapsed()
                    while not (trace.response_ordered() and trace.input_covered(turn['required_asr_patterns'])):
                        if trace.end:
                            raise ProviderEnded('Provider ended before current reply')
                        if elapsed() - wait_start > 40:
                            observe('timeout', code='current_response_absent')
                            raise TimeoutError('Current ASR/response/audio absent')
                        await tick()
                all_sent = True
                # Late split-ASR or interruption invalidates readiness. Closing the socket is
                # not a substitute for the final spoken acknowledgement.
                while not (trace.drained(elapsed()) and trace.input_covered(case['turns'][-1]['required_asr_patterns'])):
                    if trace.end and not (trace.response_ordered() and trace.input_covered(case['turns'][-1]['required_asr_patterns'])):
                        raise ProviderEnded('Provider ended without final acknowledgement')
                    await tick()
            except ProviderEnded:
                pass
            except Exception as error:  # noqa: BLE001 - sanitize network/provider failures
                if not isinstance(error, TimeoutError):
                    observe('harness_error', code=type(error).__name__)
            finally:
                if not receiver.done() and not trace.end:
                    observe('harness_disconnect', reason='probe_complete_or_cap')
                    try:
                        await socket.close()
                    except ConnectionClosedOK:
                        pass
                await receiver
    except ConnectionClosedOK as error:
        close = error.rcvd or error.sent
        observe('provider_end', code=close.code if close else None,
                reason=safe_close_reason(close.reason if close else 'no_reason'))
    except Exception as error:  # noqa: BLE001 - sanitize network/provider failures
        observe('harness_error', code=type(error).__name__)
    finally:
        state['events'] = trace.events
        state['provider_end'] = trace.end
        state['close_initiator'] = 'harness' if any(e['type'] == 'harness_disconnect' for e in trace.events) else 'provider'
        state['all_inputs_sent'] = sum(e['type'] == 'input_end' for e in trace.events) == len(case['turns'])
        state['final_input_covered'] = trace.input_covered(case['turns'][-1]['required_asr_patterns'])
        state['transport'] = trace.transport_verdict(elapsed(), all_sent,
                                                   input_covered=state['final_input_covered'])
        state['script_completed'] = state['transport']['status'] == 'completed'
        state['audio_bytes'] = len(audio)
        state['audio_nonzero'] = any(audio)
        state['audio_seconds_received'] = len(audio) / (2 * audio_rate) if audio_rate else 0
        state['elapsed_seconds'] = round(elapsed(), 3)
        state['discarded_audio_bytes'] = trace.discarded_bytes
        state['final_audio_association'] = 'absent'
        state['final_spoken_content'] = spoken_grade(case, trial_root / 'final-received.wav')
        state['validity_class'] = trial_validity(state['transport'], state['final_spoken_content'])
        if audio_rate and audio:
            wav(trial_root / 'agent-received.wav', audio, audio_rate)
            # Only the temporally associated final reply, never earlier queued speech, is
            # eligible for final-required-content STT. This still is not physical playback.
            final_events = [e for e in trace.events if e['type'] == 'audio' and not e['discarded']
                            and e['at'] >= trace.agent_at and e['association'] != 'mismatch']
            chunks = [audio[e['stream_offset']:e['stream_offset'] + e['bytes']] for e in final_events]
            state['final_audio_association'] = ('explicit' if final_events and all(e['association'] == 'explicit' for e in final_events)
                                                else 'temporal_only' if final_events else 'absent')
            wav(trial_root / 'final-received.wav', b''.join(chunks), audio_rate)
            state['final_audio_sha256'] = file_digest(trial_root / 'final-received.wav')
        if state.get('conversation_id'):
            try:
                state['persistent_outcome'] = read_outcome(evaluation_root, state['conversation_id'])
            except (OSError, ValueError, sqlite3.Error) as error:
                state['persistent_outcome'] = {'status': 'unverified', 'error_type': type(error).__name__}
        state['business_state'] = business_state_grade(case, state.get('persistent_outcome', {}), trace.events)
        state['case_acceptance'] = 'failed' if state['business_state']['status'] == 'fail' else 'pending_independent_review'
        save(output, state)
    print(json.dumps({k: state.get(k) for k in ('conversation_id', 'transport', 'validity_class', 'audio_seconds_received')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['generate', 'run', 'grade-audio'])
    parser.add_argument('--output', type=Path, required=True, help='Versioned fixture root')
    parser.add_argument('--case', type=Path, required=True)
    parser.add_argument('--agent-id')
    parser.add_argument('--evaluation-root', type=Path)
    parser.add_argument('--provision-manifest', type=Path)
    parser.add_argument('--trial-id')
    parser.add_argument('--spoken-evidence', type=Path)
    args = parser.parse_args()
    case = load_case(args.case)
    if args.trial_id and not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.trial_id):
        parser.error('trial-id must be a bounded identifier, not a path')
    if args.action == 'grade-audio':
        if not args.trial_id or not args.spoken_evidence:
            parser.error('grade-audio requires trial-id and spoken-evidence')
        trial = args.output / 'trials' / args.trial_id
        state = json.loads((trial / 'audio-run.json').read_text())
        if state.get('trial_id') != args.trial_id or state['case_sha256'] != digest(case):
            raise ValueError('Wrong case for audio grade')
        grade_path = trial / 'spoken-grade.json'
        if grade_path.exists():
            raise ValueError('Grade already exists; preserve prior outcome')
        final_audio = trial / 'final-received.wav'
        if final_audio.is_symlink() or not state.get('final_audio_sha256') or file_digest(final_audio) != state['final_audio_sha256']:
            raise ValueError('Final audio differs from the recorded run artifact')
        grade = spoken_grade(case, final_audio, json.loads(args.spoken_evidence.read_text()),
                             state.get('final_audio_association', 'unverified'))
        business = business_state_grade(case, state.get('persistent_outcome', {}), state.get('events', []))
        save(grade_path, {'case_sha256': digest(case), 'trial_id': args.trial_id, 'grade': grade,
                          'transport': state['transport'], 'validity_class': trial_validity(state['transport'], grade),
                          'business_state': business,
                          'case_acceptance': 'failed' if business['status'] == 'fail' else 'pending_independent_review',
                          'harness_version': HARNESS_VERSION})
        print(json.dumps(grade))
        return
    if args.action == 'run' and not all((args.agent_id, args.evaluation_root, args.provision_manifest, args.trial_id)):
        parser.error('run requires explicit agent-id, evaluation-root, provision-manifest and trial-id')
    validate_case_clock(case)
    load_dotenv('.env')
    client = ElevenLabs(api_key=os.environ['ELEVENLABS_API_KEY'])
    try:
        if args.action == 'generate':
            generate(client, args.output, case)
        else:
            asyncio.run(asyncio.wait_for(run(client, args.output, case, args.agent_id,
                                            args.evaluation_root, args.provision_manifest, args.trial_id),
                                         case['max_seconds'] + 30))
    except Exception as error:  # noqa: BLE001 - network exceptions may contain signed URLs
        print('Audio probe stopped:', type(error).__name__, '; inspect persisted pending state')
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
