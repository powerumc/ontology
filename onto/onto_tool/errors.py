class OntoError(Exception):
    """사용자에게 그대로 보여 줄 오류. 명령줄 진입점이 메시지마다 한 줄로 알리고 0이 아닌 종료 코드로 끝낸다."""

    def __init__(self, *messages: str) -> None:
        super().__init__("\n".join(messages))
        self.messages = list(messages)
