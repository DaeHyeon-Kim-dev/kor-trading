"""pykrx KRX 로그인 자격증명 주입.

KRX data 포털(data.krx.co.kr)이 데이터 조회에 로그인을 의무화함(2025+).
pykrx 1.2.8은 KRX_ID/KRX_PW 환경변수로 자동 로그인하므로, 데이터 요청 전에
환경변수를 설정해 두면 첫 호출 시 pykrx가 세션을 만든다.

자격증명이 없으면 아무것도 하지 않는다 (pykrx는 비로그인 → "LOGOUT" 응답 → 실패).
"""

from __future__ import annotations

import os

import structlog

log = structlog.get_logger()


def configure_krx_login(krx_id: str | None, krx_pw: str | None) -> bool:
    """KRX 자격증명을 환경변수로 주입. 설정 여부를 반환.

    pykrx의 get_auth_session()이 _auth_session=None일 때 os.environ에서
    KRX_ID/KRX_PW를 읽어 로그인하므로, import 시점과 무관하게 동작한다.
    """
    if not (krx_id and krx_pw):
        log.warning("krx_auth.no_credentials")
        return False
    os.environ["KRX_ID"] = krx_id
    os.environ["KRX_PW"] = krx_pw
    log.info("krx_auth.configured", krx_id=krx_id)
    return True
