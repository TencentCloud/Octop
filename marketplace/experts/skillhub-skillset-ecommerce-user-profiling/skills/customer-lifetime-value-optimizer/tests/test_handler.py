#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from handler import CustomerLifetimeValueOptimizer, handle


def test_segment_detection_vip_and_dormant():
    optimizer = CustomerLifetimeValueOptimizer('We need a plan for VIP members and dormant customers who stopped ordering.')
    assert 'High-value loyal customers' in optimizer.segments
    assert 'Dormant customers' in optimizer.segments


def test_primary_lever_detection_raise_aov():
    optimizer = CustomerLifetimeValueOptimizer('Need to improve bundle attach rate, upsell, and average order value without hurting margin.')
    assert optimizer.primary_lever == 'Raise AOV'


def test_render_contains_sections():
    output = handle('Build an LTV plan for new customers, VIP members, and price-sensitive customers.')
    assert output.startswith('# LTV Optimization Plan')
    assert '## Segment Diagnosis' in output
    assert '## Action Packages' in output


def test_dict_input_supported():
    output = handle({
        'segments': ['new customers', 'VIP members', 'dormant customers'],
        'focus': 'repeat rate and margin',
        'constraints': 'avoid over-discounting',
    })
    assert '# LTV Optimization Plan' in output
    assert 'avoid over-discounting' in output


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('All tests passed.')
