#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from handler import PromotionEnrollmentAssistant, handle


def test_platform_detection_amazon():
    assistant = PromotionEnrollmentAssistant('Amazon Lightning Deal enrollment for Prime Day')
    assert assistant.platform == 'Amazon'


def test_platform_detection_tiktok():
    assistant = PromotionEnrollmentAssistant('TikTok Shop flash sale enrollment')
    assert assistant.platform == 'TikTok Shop'


def test_promo_type_detection_lightning_deal():
    assistant = PromotionEnrollmentAssistant('Amazon Lightning Deal')
    assert assistant.promo_type == 'Lightning Deal'


def test_promo_type_detection_jd_618():
    assistant = PromotionEnrollmentAssistant('JD 618 promotion enrollment')
    assert assistant.promo_type == 'JD 618'


def test_render_contains_sections():
    output = handle('Help me enroll in Amazon Lightning Deal for our skincare SKU this Prime Day')
    assert output.startswith('# Promotion Enrollment Brief')
    assert '## How It Works' in output
    assert '## Enrollment Timeline' in output
    assert '## Common Rejection Reasons' in output


def test_dict_input_supported():
    output = handle({
        'platform': 'Amazon',
        'promo_type': 'Lightning Deal',
        'sku': 'skincare-serum-30ml',
        'window': 'Prime Day'
    })
    assert '# Promotion Enrollment Brief' in output
    assert 'Lightning Deal' in output


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('All tests passed.')
