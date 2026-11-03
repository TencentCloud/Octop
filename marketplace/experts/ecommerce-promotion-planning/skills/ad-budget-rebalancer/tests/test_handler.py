#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from handler import AdBudgetRebalancer, handle


def test_channel_detection_meta():
    rebalancer = AdBudgetRebalancer('Review our Meta Ads ROAS and reallocate budget')
    assert 'Meta Ads' in rebalancer.channels


def test_channel_detection_google_tiktok():
    rebalancer = AdBudgetRebalancer('Rebalance budget across Google and TikTok')
    assert 'Google Ads' in rebalancer.channels
    assert 'TikTok Ads' in rebalancer.channels


def test_campaign_type_detection():
    rebalancer = AdBudgetRebalancer('Awareness campaigns on Meta and conversion campaigns on Google')
    assert 'Awareness' in rebalancer.campaign_types
    assert 'Conversion' in rebalancer.campaign_types


def test_concern_detection_performance_decline():
    rebalancer = AdBudgetRebalancer('Our ROAS dropped this month on TikTok')
    assert rebalancer.concern == 'Performance Decline'


def test_render_contains_sections():
    output = handle('Our Meta Ads ROAS dropped this month — should we reallocate budget?')
    assert output.startswith('# Ad Budget Rebalancing Brief')
    assert '## Channel Efficiency Scorecard' in output
    assert '## Rebalancing Recommendations' in output


def test_dict_input_supported():
    output = handle({
        'budget': '50k',
        'channels': ['Meta Ads', 'Google Ads', 'Amazon Sponsored'],
        'performance': {'Meta': 'ROAS 1.8', 'Google': 'ROAS 3.2'},
        'concern': 'Periodic Review'
    })
    assert '# Ad Budget Rebalancing Brief' in output
    assert 'Meta Ads' in output


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('All tests passed.')
