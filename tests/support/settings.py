"""테스트가 함께 쓰는 설정값.

앱을 만드는 테스트는 tests/conftest.py의 `app_env` fixture로 아래 값을 환경변수에 넣는다.
설정을 준비하는 방법이 테스트마다 갈라지지 않게 하기 위해서다.
"""

from app.core.config import Settings

TEST_FRONTEND_URL = "http://localhost:5173"
TEST_GOOGLE_CLIENT_ID = "test-client-id.apps.googleusercontent.com"
# 로그에 비밀값이 남았는지 찾을 때 다른 문자열과 헷갈리지 않도록 고유한 값을 쓴다.
TEST_GOOGLE_CLIENT_SECRET = "test-google-client-secret-4f9a"
# 포트 1에는 PostgreSQL이 없다. 단위 테스트가 실수로 데이터베이스에 닿으면 조용히 통과하지 않고
# 연결 오류로 드러난다. 통합 테스트는 이 값을 컨테이너의 주소로 바꾼다.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://diegesis:diegesis@127.0.0.1:1/diegesis"

# 설정 클래스가 읽는 환경변수의 이름. 테스트는 이 이름들을 지운 뒤 필요한 값만 넣는다. 개발자의
# 셸에 같은 이름의 값이 있으면 테스트 결과가 사람마다 달라지기 때문이다. 설정 클래스에 값을 더하면
# 이 목록에도 저절로 들어간다.
SETTING_ENV_NAMES = tuple(name.upper() for name in Settings.model_fields)
