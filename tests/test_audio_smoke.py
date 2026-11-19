"""Deterministic regressions for actual audio races, closure and isolated trial targets."""
import importlib.util
import json
from pathlib import Path

import pytest

from fil_shop.audio_evaluation import (
    AudioTrace,
    business_state_grade,
    digest,
    file_digest,
    load_case,
    provider_digest,
    read_outcome,
    response_follows_input,
    spoken_grade,
    trial_validity,
    validate_case_clock,
    validate_target,
)
from fil_shop.evaluation import EvaluationStore

spec = importlib.util.spec_from_file_location(
    'audio_smoke', Path(__file__).resolve().parents[1] / 'scripts/audio_smoke.py',
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_old_response_arriving_during_caller_audio_is_not_completion():
    assert not response_follows_input(15.783, 20.207, 16.161, 20.22)


def test_new_asr_segment_invalidates_previous_reply():
    trace = AudioTrace()
    trace.observe('input_start', 48, id='english')
    trace.observe('user_transcript', 50, text='Back to English')
    trace.observe('agent_response', 51, text='Sure')
    trace.observe('audio', 52, bytes=3200, rate=16000, event_id=1)
    assert trace.drained(54)
    trace.observe('user_transcript', 59, text='Delivery to Barcelona')
    trace.observe('audio', 60, bytes=3200, rate=16000, event_id=2)
    assert not trace.drained(62)
    trace.observe('agent_response', 63, text='Checking Barcelona')
    trace.observe('audio', 64, bytes=3200, rate=16000, event_id=3)
    assert trace.drained(66)


def test_delayed_audio_and_prior_caller_turn_cannot_pass():
    assert not response_follows_input(10, 14, 15, 13)
    assert response_follows_input(10, 14, 15, 16)
    assert not response_follows_input(20, 14, 15, 22)
    trace = AudioTrace()
    trace.observe('input_start', 1, id='request')
    trace.observe('user_transcript', 2, text='A shirt')
    trace.observe('agent_response', 3, text='Here it is')
    assert trace.transport_verdict(10, True)['status'] == 'incomplete'
    trace.observe('audio', 12, bytes=64000, rate=16000, event_id=1)
    assert not trace.drained(13)
    assert trace.drained(15)


def completed_trace():
    trace = AudioTrace()
    trace.observe('input_start', 1, id='goodbye')
    trace.observe('user_transcript', 2, text='Goodbye')
    trace.observe('agent_response', 3, text='Goodbye, have a nice day')
    trace.observe('audio', 4, bytes=32000, rate=16000, event_id=10)
    return trace


def test_buffer_interruption_discards_old_chunks_and_invalidates_reply():
    trace = completed_trace()
    trace.observe('interruption', 4.1, event_id=10)
    old = trace.observe('audio', 4.2, bytes=64000, rate=16000, event_id=10)
    assert old['discarded'] and trace.discarded_bytes == 64000
    assert trace.received_bytes == 32000
    assert trace.transport_verdict(10, True)['status'] == 'incomplete'
    trace.observe('user_transcript', 5, text='Actually, goodbye')
    trace.observe('agent_response', 6, text='Goodbye')
    trace.observe('audio', 7, bytes=3200, rate=16000, event_id=11)
    assert trace.drained(9)


def test_goodbye_provider_end_does_not_invent_final_acknowledgement():
    trace = completed_trace()
    trace.observe('interruption', 4.1, event_id=10)
    trace.observe('user_transcript', 4.5, text='Thank you goodbye')
    trace.observe('provider_end', 5, code=1000, reason='normal')
    assert trace.transport_verdict(20, True) == {
        'status': 'incomplete', 'reason': 'final_response_absent_or_interrupted'}


def test_provider_end_after_complete_final_reply_can_finish_but_needs_spoken_evidence():
    trace = completed_trace()
    trace.observe('provider_end', 5.5, code=1000, reason='agent ended')
    assert trace.transport_verdict(6, True)['status'] == 'completed'
    assert spoken_grade({'final_required_spoken_patterns': ['goodbye']}, Path('missing.wav'))['status'] == 'uncertain'


@pytest.mark.parametrize('kind', ['timeout', 'harness_error', 'provider_error'])
def test_timeout_or_error_cannot_become_a_completion(kind):
    trace = completed_trace()
    trace.observe(kind, 6, code='test')
    assert trace.transport_verdict(20, True)['status'] == 'incomplete'


def test_tool_error_is_observed_not_automatically_a_harness_failure():
    trace = AudioTrace()
    trace.observe('input_start', 1, id='outage')
    trace.observe('user_transcript', 2, text='Can you check stock')
    trace.observe('tool_error', 3, tool_name='check_variant', code='inventory_unavailable')
    trace.observe('agent_response', 4, text='I cannot confirm inventory')
    trace.observe('audio', 5, bytes=3200, rate=16000, event_id=1)
    assert trace.transport_verdict(8, True)['status'] == 'completed'
    assert trace.errors[0]['type'] == 'tool_error'


def test_abnormal_close_fails_even_after_audio():
    trace = completed_trace()
    trace.observe('provider_end', 6, code=1011, reason='provider failure')
    assert trace.transport_verdict(8, True)['reason'] == 'abnormal_provider_end'


def provision(root):
    return {'schema': 1, 'purpose': 'fil-audio-evaluation', 'agent_id': 'eval-agent',
            'evaluation_root': str(root), 'agent_snapshot_sha256': 'a' * 64,
            'tool_ids': {'search_products': 'search', 'check_variant': 'check', 'reserve_variant': 'reserve'},
            'tool_snapshot_sha256': {'search_products': 'b' * 64, 'check_variant': 'c' * 64,
                                     'reserve_variant': 'd' * 64}}


def test_target_requires_provisioned_isolated_root_and_rejects_live(tmp_path):
    root = tmp_path / 'eval'
    EvaluationStore(root)
    manifest = provision(root)
    assert validate_target(manifest, 'eval-agent', root, 'live-agent') == root.resolve()
    with pytest.raises(ValueError, match='Live agent'):
        validate_target(manifest, 'live-agent', root, 'live-agent')
    with pytest.raises(ValueError, match='Set ELEVENLABS_AGENT_ID'):
        validate_target(manifest, 'eval-agent', root, None)
    with pytest.raises(ValueError):
        validate_target(manifest, 'eval-agent', tmp_path / 'live', 'live-agent')
    with pytest.raises(ValueError):
        validate_target({**manifest, 'purpose': 'production'}, 'eval-agent', root, 'live-agent')
    with pytest.raises(ValueError):
        validate_target({**manifest, 'tool_snapshot_sha256': {}}, 'eval-agent', root, 'live-agent')


def test_read_outcome_uses_provider_conversation_digest_and_never_creates_store(tmp_path):
    root = tmp_path / 'eval'
    router = EvaluationStore(root)
    assert read_outcome(root.resolve(), 'unexercised')['status'] == 'not_exercised'
    assert list(root.glob('*.sqlite')) == []
    store = router('actual-provider-id')
    criteria = {'category': 'shirt', 'occasion': 'wedding', 'max_price_cents': 12000,
                'colour': 'navy', 'size': 'M'}
    store.search('actual-provider-id', criteria)
    result = read_outcome(root.resolve(), 'actual-provider-id')
    assert result['criteria'] == criteria and result['reservations'] == []
    assert read_outcome(root.resolve(), 'different-provider-id')['status'] == 'not_exercised'
    with pytest.raises(ValueError):
        read_outcome(root.resolve(), '../live')


def test_six_versioned_audio_cases_are_explicit_and_independent_of_live_targets():
    root = Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2'
    cases = [load_case(p) for p in root.glob('*.json')]
    assert len(cases) == 6 and len({c['id'] for c in cases}) == 6
    assert all(c['final_required_spoken_patterns'] for c in cases)
    assert sum(t['send_mode'] == 'overlap' for c in cases for t in c['turns']) == 1
    assert not hasattr(module, 'LINES')


def test_audio_fixture_tampering_and_case_change_are_rejected(tmp_path):
    case = {'id': 'test', 'version': 1, 'turns': [{'id': 'one'}]}
    module.wav(tmp_path / 'caller-0.wav', bytes(3200), 16000)
    manifest = {'schema': 2, 'case': case, 'case_sha256': digest(case),
                'fixtures': [{'turn_id': 'one', 'file': 'caller-0.wav',
                              'sha256': file_digest(tmp_path / 'caller-0.wav')}]}
    (tmp_path / 'fixtures.json').write_text(json.dumps(manifest))
    assert module.load_fixtures(tmp_path, case) == manifest
    with pytest.raises(ValueError):
        module.load_fixtures(tmp_path, {**case, 'version': 2})
    (tmp_path / 'caller-0.wav').write_bytes(b'changed')
    with pytest.raises(ValueError):
        module.load_fixtures(tmp_path, case)


def test_spoken_grade_requires_exact_final_audio_and_detects_truncation(tmp_path):
    audio = tmp_path / 'final.wav'
    module.wav(audio, bytes(3200), 16000)
    case = {'final_required_spoken_patterns': ['goodbye|have a nice day']}
    base = {'audio_sha256': file_digest(audio), 'transcriber_version': 'test-stt-v1'}
    assert spoken_grade(case, audio, {**base, 'text': 'Understood, I won'}, 'explicit')['status'] == 'fail'
    assert spoken_grade(case, audio, {**base, 'text': 'Goodbye, take care'}, 'explicit')['status'] == 'pass'
    with pytest.raises(ValueError):
        spoken_grade(case, audio, {**base, 'audio_sha256': 'wrong', 'text': 'Goodbye'})


def test_provider_fingerprints_ignore_metadata_but_detect_prompt_or_tools():
    agent = {'agent_id': 'eval', 'conversation_config': {'prompt': 'one'}, 'metadata': {'count': 1}}
    assert provider_digest(agent, 'agent') == provider_digest({**agent, 'metadata': {'count': 2}}, 'agent')
    assert provider_digest(agent, 'agent') != provider_digest({**agent, 'conversation_config': {'prompt': 'two'}}, 'agent')
    tool = {'id': 'tool', 'tool_config': {'url': 'https://evaluation.invalid'}}
    assert provider_digest(tool, 'tool') != provider_digest({**tool, 'tool_config': {'url': 'https://live.invalid'}}, 'tool')


def test_final_spoken_words_cannot_pass_an_interrupted_or_incomplete_trial():
    assert trial_validity({'status': 'incomplete'}, {'status': 'pass'}) == 'incomplete'
    assert trial_validity({'status': 'completed'}, {'status': 'uncertain'}) == 'awaiting_spoken_content_review'
    assert trial_validity({'status': 'completed'}, {'status': 'fail'}) == 'required_spoken_content_failed'
    assert trial_validity({'status': 'completed'}, {'status': 'pass'}) == 'audio_content_present_semantics_pending'


def test_frozen_audio_dates_expire_instead_of_silently_rewriting_inputs():
    from datetime import date
    case = {'date_window': {'deadline': '2026-11-20', 'last_start_date': '2026-11-19'}}
    validate_case_clock(case, date(2026, 11, 6))
    with pytest.raises(ValueError, match='expired'):
        validate_case_clock(case, date(2026, 11, 20))


def test_late_goodbye_asr_required_before_previous_refusal_can_complete_fixture():
    trace = AudioTrace()
    trace.observe('input_start', 1, id='refusal-and-bye')
    trace.observe('user_transcript', 2, text='Do not reserve')
    trace.observe('agent_response', 3, text='Understood')
    trace.observe('audio', 4, bytes=3200, rate=16000, event_id=1)
    assert trace.drained(6)
    assert not trace.input_covered(['do not reserve', 'goodbye'])
    trace.observe('user_transcript', 7, text='Thank you goodbye')
    assert trace.input_covered(['do not reserve', 'goodbye'])
    assert not trace.response_ordered()


def test_explicit_audio_identity_and_ambiguous_temporal_association_are_distinct(tmp_path):
    trace = AudioTrace()
    trace.observe('input_start', 1, id='bye')
    trace.observe('user_transcript', 2, text='Goodbye')
    trace.observe('agent_response', 3, text='Goodbye', response_id='r2')
    old = trace.observe('audio', 4, bytes=3200, rate=16000, event_id=1, response_id='r1')
    assert old['association'] == 'mismatch' and not trace.response_ordered()
    actual = trace.observe('audio', 5, bytes=3200, rate=16000, event_id=2, response_id='r2')
    assert actual['association'] == 'explicit' and trace.response_ordered()
    audio = tmp_path / 'final.wav'
    module.wav(audio, bytes(3200), 16000)
    evidence = {'audio_sha256': file_digest(audio), 'transcriber_version': 'stt-v1', 'text': 'Goodbye'}
    case = {'final_required_spoken_patterns': ['goodbye']}
    result = spoken_grade(case, audio, evidence, 'temporal_only')
    assert result['status'] == 'uncertain' and result['content_match']
    assert spoken_grade(case, audio, evidence, 'explicit')['status'] == 'pass'


def test_run_rejects_live_before_any_provider_or_signed_url_access(tmp_path, monkeypatch):
    monkeypatch.setenv('ELEVENLABS_AGENT_ID', 'live-agent')
    import asyncio
    root = tmp_path / 'eval'
    EvaluationStore(root)
    path = tmp_path / 'provision.json'
    path.write_text(json.dumps(provision(root)))
    with pytest.raises(ValueError, match='Live agent'):
        asyncio.run(module.run(object(), tmp_path, {}, 'live-agent', root, path, 'trial-1'))


def test_grade_cli_rejects_replaced_wav_even_when_new_stt_hash_matches(tmp_path, monkeypatch):
    case_path = Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2/closing.json'
    case = load_case(case_path)
    trial = tmp_path / 'trials' / 'trial-1'
    trial.mkdir(parents=True)
    audio = trial / 'final-received.wav'
    module.wav(audio, bytes(3200), 16000)
    state = {'trial_id': 'trial-1', 'case_sha256': digest(case), 'final_audio_sha256': file_digest(audio),
             'final_audio_association': 'explicit', 'transport': {'status': 'completed'}}
    (trial / 'audio-run.json').write_text(json.dumps(state))
    module.wav(audio, bytes(6400), 16000)
    evidence = tmp_path / 'stt.json'
    evidence.write_text(json.dumps({'audio_sha256': file_digest(audio), 'text': 'Goodbye',
                                    'transcriber_version': 'test-stt'}))
    monkeypatch.setattr('sys.argv', ['audio_smoke.py', 'grade-audio', '--output', str(tmp_path),
                                     '--case', str(case_path), '--trial-id', 'trial-1',
                                     '--spoken-evidence', str(evidence)])
    with pytest.raises(ValueError, match='recorded run artifact'):
        module.main()
    assert not (trial / 'spoken-grade.json').exists()


@pytest.mark.parametrize('text', ['have a nice', 'have a good', 'understood, I won', 'byelaw'])
def test_closing_content_control_rejects_truncated_or_substring_farewell(tmp_path, text):
    case = load_case(Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2/closing.json')
    audio = tmp_path / 'final.wav'
    module.wav(audio, bytes(3200), 16000)
    evidence = {'audio_sha256': file_digest(audio), 'text': text, 'transcriber_version': 'test-stt'}
    assert spoken_grade(case, audio, evidence, 'explicit')['status'] == 'fail'


@pytest.mark.parametrize('text', ['Goodbye.', 'Have a nice day.', 'Take care!'])
def test_closing_content_control_accepts_complete_farewell(tmp_path, text):
    case = load_case(Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2/closing.json')
    audio = tmp_path / 'final.wav'
    module.wav(audio, bytes(3200), 16000)
    evidence = {'audio_sha256': file_digest(audio), 'text': text, 'transcriber_version': 'test-stt'}
    assert spoken_grade(case, audio, evidence, 'explicit')['status'] == 'pass'


def test_positive_keywords_never_establish_semantic_success_or_override_wrong_state(tmp_path):
    case = load_case(Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2/positive-consent.json')
    audio = tmp_path / 'final.wav'
    module.wav(audio, bytes(3200), 16000)
    evidence = {'audio_sha256': file_digest(audio), 'text': 'The hold was not placed.',
                'transcriber_version': 'test-stt'}
    content = spoken_grade(case, audio, evidence, 'explicit')
    assert content['content_match'] and content['semantic_acceptance'] == 'uncertain'
    assert trial_validity({'status': 'completed'}, content) == 'audio_content_present_semantics_pending'
    business = business_state_grade(case, {'status': 'observed', 'reservations': [], 'criteria': {}}, [])
    assert business['status'] == 'fail'


def test_business_state_checks_actual_outcome_and_keeps_transient_actions_unknown():
    case = {'expected_state': {'reservations': 0, 'colour': 'sage', 'size': 'L'}}
    outcome = {'status': 'observed', 'criteria': {'colour': 'sage', 'size': 'L'}, 'reservations': []}
    result = business_state_grade(case, outcome, [])
    assert result['status'] == 'uncertain'
    assert next(c for c in result['criteria'] if c['criterion'] == 'reservations')['status'] == 'pass'
    assert business_state_grade(case, outcome, [{'type': 'tool_error', 'tool_name': 'reserve_variant'}])['status'] == 'fail'
    assert business_state_grade(case, {**outcome, 'criteria': {'colour': 'navy', 'size': 'M'}}, [])['status'] == 'fail'


def test_inventory_error_expected_state_requires_actual_persisted_error():
    case = {'expected_state': {'reservations': 0, 'required_tool_error': 'inventory_unavailable'}}
    good = {'status': 'observed', 'reservations': [], 'error': 'inventory_unavailable'}
    assert business_state_grade(case, good, [])['status'] == 'uncertain'  # absent-action trace not complete
    assert business_state_grade(case, {**good, 'error': None}, [])['status'] == 'fail'


@pytest.mark.parametrize('kind', ['backchannel', 'sentence_pause', 'background_speech'])
def test_unsupported_response_policy_is_rejected_not_claimed_covered(tmp_path, kind):
    original = Path(__file__).resolve().parents[1] / 'agent/audio-evaluation-v2/closing.json'
    case = json.loads(original.read_text())
    case['turns'][0]['kind'] = kind
    path = tmp_path / 'unsupported.json'
    path.write_text(json.dumps(case))
    with pytest.raises(ValueError, match='turn contract'):
        load_case(path)


@pytest.mark.parametrize(('has_farewell', 'has_asr'), [(False, True), (True, True), (True, False)])
def test_normal_websocket_close_racing_silence_send_preserves_real_completion(tmp_path, monkeypatch, has_farewell, has_asr):
    """Exercise the actual runner, including a send/receiver race, without a provider."""
    import asyncio
    import base64
    from types import SimpleNamespace

    from websockets.exceptions import ConnectionClosedOK
    from websockets.frames import Close

    class Clock:
        now = 0.0

        def monotonic(self):
            return self.now

    clock = Clock()
    real_sleep = asyncio.sleep

    async def advance(seconds):
        clock.now += seconds
        await real_sleep(0)

    class FakeSocket:
        close_code = None
        close_reason = None
        voice_seen = False
        raced_close = False

        def __init__(self):
            self.events = asyncio.Queue()
            self.events.put_nowait({'type': 'conversation_initiation_metadata',
                                   'conversation_initiation_metadata_event': {
                                       'conversation_id': 'provider-close-regression',
                                       'user_input_audio_format': 'pcm_16000',
                                       'agent_output_audio_format': 'pcm_16000'}})
            self.events.put_nowait({'type': 'agent_response', 'agent_response_event': {
                'agent_response': 'Hello', 'response_id': 'greeting'}})
            self.events.put_nowait(self.audio('greeting', 1))

        @staticmethod
        def audio(response, event_id):
            return {'type': 'audio', 'audio_event': {'audio_base_64': base64.b64encode(b'\x01\x00' * 1600).decode(),
                                                    'event_id': event_id, 'response_id': response}}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        def __aiter__(self):
            return self

        async def __anext__(self):
            event = await self.events.get()
            clock.now += .01
            if event is None:
                raise StopAsyncIteration
            return json.dumps(event)

        async def send(self, value):
            event = json.loads(value)
            if 'user_audio_chunk' not in event:
                return
            pcm = base64.b64decode(event['user_audio_chunk'])
            if any(pcm):
                self.voice_seen = True
                if has_asr:
                    self.events.put_nowait({'type': 'user_transcript', 'user_transcription_event': {'user_transcript': 'Goodbye'}})
                return
            if self.voice_seen and not self.raced_close:
                self.raced_close = True
                self.close_code, self.close_reason = 1000, 'agent ended normally'
                if has_farewell:
                    self.events.put_nowait({'type': 'agent_response', 'agent_response_event': {
                        'agent_response': 'Goodbye, take care.', 'response_id': 'farewell'}})
                    self.events.put_nowait(self.audio('farewell', 2))
                self.events.put_nowait(None)
                # Receiver has not consumed the queued ending; exactly the observed race.
                close = Close(1000, self.close_reason)
                raise ConnectionClosedOK(close, close, True)

        async def close(self):
            self.close_code, self.close_reason = 1000, 'harness close'
            self.events.put_nowait(None)

    fixture_root = tmp_path / 'fixtures'
    fixture_root.mkdir()
    evaluation_root = tmp_path / 'isolated'
    EvaluationStore(evaluation_root)
    provision_path = tmp_path / 'provision.json'
    provision_path.write_text(json.dumps(provision(evaluation_root)))
    case = {'id': 'close-regression', 'version': 1, 'max_seconds': 30,
            'turns': [{'id': 'bye', 'language': 'en', 'text': 'Goodbye', 'kind': 'goodbye',
                       'send_mode': 'after_response', 'required_asr_patterns': ['goodbye']}],
            'final_required_spoken_patterns': [r'\bgoodbye\b'], 'expected_state': {'reservations': 0}}
    module.wav(fixture_root / 'caller-0.wav', b'\x01\x00' * 1600, 16000)
    (fixture_root / 'fixtures.json').write_text(json.dumps({
        'schema': 2, 'case': case, 'case_sha256': digest(case), 'fixtures': [{
            'turn_id': 'bye', 'file': 'caller-0.wav', 'sha256': file_digest(fixture_root / 'caller-0.wav')}]}))
    socket = FakeSocket()
    client = SimpleNamespace(conversational_ai=SimpleNamespace(conversations=SimpleNamespace(
        get_signed_url=lambda **_: SimpleNamespace(signed_url='wss://synthetic.invalid'))))
    monkeypatch.setattr(module, 'time', clock)
    monkeypatch.setattr(module.asyncio, 'sleep', advance)
    monkeypatch.setattr(module, 'connect', lambda *_, **__: socket)
    monkeypatch.setattr(module, 'verify_provider', lambda *_: None)
    monkeypatch.setenv('ELEVENLABS_AGENT_ID', 'live-agent')
    asyncio.run(module.run(client, fixture_root, case, 'eval-agent', evaluation_root, provision_path, 'normal-close'))
    state = json.loads((fixture_root / 'trials/normal-close/audio-run.json').read_text())
    assert socket.raced_close and state['provider_end']['code'] == 1000
    assert state['close_initiator'] == 'provider' and state['all_inputs_sent']
    assert not [e for e in state['events'] if e['type'] in {'harness_error', 'provider_error'}]
    if has_farewell and has_asr:
        assert state['transport']['status'] == 'completed' and state['script_completed']
        assert state['final_spoken_content']['status'] == 'uncertain'  # independent STT still required
    else:
        assert state['transport'] == {'status': 'incomplete', 'reason': 'final_response_absent_or_interrupted'}
        assert not state['script_completed']


def test_normal_close_cannot_complete_partially_recognized_caller_input():
    trace = completed_trace()
    trace.observe('provider_end', 6, code=1000, reason='normal')
    assert trace.transport_verdict(8, True, input_covered=False) == {
        'status': 'incomplete', 'reason': 'caller_input_not_fully_recognized'}
