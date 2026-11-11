"""명령줄의 하위 명령. 명령 하나가 모듈 하나다.

새 명령은 모듈을 만들어 아래 규약을 따르고, `cli.COMMANDS`에 더한다.

- `NAME`: 하위 명령의 이름
- `HELP`: 한 줄 설명
- `add_arguments(parser)`: 인자를 정의한다
- `run(args) -> int`: 명령을 실행하고 종료 코드를 돌려준다. 사용자에게 알릴 오류는 `OntoError`로 던진다
"""
