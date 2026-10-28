import json

from anystability import floating_equilibrium_worker as worker


def test_worker_writes_structured_refusal_not_a_pose_for_bad_input(tmp_path):
    source, target = tmp_path / 'in.json', tmp_path / 'out.json'
    source.write_text(json.dumps({'polygons_body_m': []}), encoding='utf-8')
    assert worker.main([str(source), str(target)]) == 1
    out = json.loads(target.read_text(encoding='utf-8'))
    assert out['status'] == 'error' and 'pose' not in out and out['message']


def test_worker_refuses_missing_input_file_atomically(tmp_path):
    target = tmp_path / 'out.json'
    assert worker.main([str(tmp_path / 'absent.json'), str(target)]) == 1
    assert json.loads(target.read_text(encoding='utf-8'))['status'] == 'error'
    assert not list(tmp_path.glob('*.tmp'))
