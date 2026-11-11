# 루트 저장소의 명령. 모듈은 각각 루트의 같은 이름 디렉토리에 있다.

mod git
mod repo
mod onto

# 인자 없이 `just`만 부르면 명령 목록을 보여 준다. 서브모듈을 바꾸는 `setup`이 기본으로 실행되지 않게 한다.
[private]
default:
    @"{{just_executable()}}" --justfile "{{justfile()}}" --list

# setup: 도구를 확인하고, 등록된 서브모듈을 초기화해 각각 추적 브랜치에 체크아웃한다.
# 추적 브랜치는 루트가 기록한 커밋에 둔다. 원격의 최신으로 올리지 않는다.
# 그 뒤 온톨로지 층(docs/ontology/ontology.yaml)이 있는 지식 저장소는 `just onto sync <이름>`으로 최신화한다. 복사된 기능(.onto/, 스킬 사본)은 지식 저장소의 커밋에
# 들어가지 않으므로 새 기기에서 클론한 저장소에는 없다. 최신화는 커밋하지 않고, 온톨로지 층이 없는 저장소는 만들지 않는다(그런 저장소는 `just onto sync`나 `just repo add`가 구성한다).
# 최신화가 실패해도 서브모듈 설정은 그대로 두고, 최신화하지 못한 저장소를 알리며 0이 아닌 종료 코드로 끝난다.

# 새로 클론한 루트 저장소를 작업할 수 있는 상태로 만든다. 도구를 확인하고 서브모듈을 추적 브랜치에 체크아웃한다.
[no-exit-message]
setup:
    #!/usr/bin/env sh
    set -eu

    # --- 도구 확인 ---
    missing=""
    for tool in git just uv; do
        command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
    done
    if [ -n "$missing" ]; then
        echo "필요한 도구가 없습니다:$missing" >&2
        exit 1
    fi

    # --- 서브모듈 초기화와 추적 브랜치 체크아웃 ---
    # 한 서브모듈의 문제로 나머지가 멈추지 않도록, 실패는 모아 두었다가 끝에 알린다.
    # 이 함수 안의 변경 명령은 set -e가 꺼지는 호출 방식(if)으로 불리므로 `|| return 1`을 직접 붙인다.
    setup_submodule() {
        name=$1
        path=$2

        # 루트가 기록한 커밋. 인덱스의 gitlink 항목은 "160000 <해시> 0<탭><경로>"이다.
        set -- $(git ls-files --stage -- "$path")
        if [ "${1:-}" != "160000" ]; then
            echo "주의: $path: .gitmodules에는 있지만 루트에 기록된 커밋이 없어 건너뛰었다" >&2
            return 0
        fi
        recorded=$2

        if [ ! -e "$path/.git" ]; then
            git submodule update --init -- "$path" || return 1
        fi

        # 이미 브랜치에 있으면 로컬 커밋이 있을 수 있으므로 건드리지 않는다.
        current=$(git -C "$path" symbolic-ref --quiet --short HEAD || true)
        if [ -n "$current" ]; then
            echo "$path: 이미 $current 브랜치에 있어 건드리지 않았다"
            return 0
        fi
        if [ "$(git -C "$path" rev-parse HEAD)" != "$recorded" ]; then
            echo "주의: $path: detached HEAD가 루트가 기록한 커밋이 아니어서 건드리지 않았다" >&2
            return 0
        fi

        # 추적 브랜치: .gitmodules에 기록된 것, 없으면 원격의 기본 브랜치.
        branch=$(git config -f .gitmodules --get "submodule.$name.branch" || true)
        if [ -z "$branch" ]; then
            branch=$(git -C "$path" symbolic-ref --quiet --short refs/remotes/origin/HEAD || true)
            branch=${branch#origin/}
        fi
        if [ -z "$branch" ]; then
            echo "주의: $path: 추적 브랜치를 알 수 없어 detached HEAD로 두었다" >&2
            return 0
        fi

        # 기록된 커밋이 원격 추적 브랜치의 이력에 없으면 브랜치를 옮기지 않는다.
        remote_ref=refs/remotes/origin/$branch
        if ! git -C "$path" merge-base --is-ancestor "$recorded" "$remote_ref" 2>/dev/null; then
            echo "주의: $path: 루트가 기록한 커밋이 origin/$branch 의 이력에 없어 detached HEAD로 두었다" >&2
            return 0
        fi

        # 로컬 브랜치는 서브모듈을 초기화하면 원격의 최신 커밋에 이미 만들어져 있다.
        # 그냥 전환하면 최신으로 올라가므로 기록된 커밋으로 옮긴다. 단, 푸시하지 않은 커밋이 있으면 옮기지 않는다.
        if tip=$(git -C "$path" rev-parse --verify --quiet "refs/heads/$branch"); then
            if ! git -C "$path" merge-base --is-ancestor "$tip" "$remote_ref"; then
                echo "주의: $path: 로컬 $branch 브랜치에 푸시하지 않은 커밋이 있어 detached HEAD로 두었다" >&2
                return 0
            fi
        fi
        git -C "$path" checkout --quiet -B "$branch" "$recorded" || return 1
        git -C "$path" branch --quiet --set-upstream-to="origin/$branch" "$branch" || return 1
        echo "$path: $branch 브랜치에 체크아웃했다 ($(printf %.7s "$recorded"))"
    }

    failed=""
    knowledge=""
    nl=$(printf '\nx')
    nl=${nl%x}
    if [ -f .gitmodules ]; then
        # 종료 코드 1은 항목이 없다는 뜻이고, 그 밖은 .gitmodules를 읽지 못한 것이다(예: 충돌 표시가 남은 경우).
        status=0
        keys=$(git config -f .gitmodules --name-only --get-regexp '^submodule\..*\.path$') || status=$?
        if [ "$status" -gt 1 ]; then
            echo "오류: .gitmodules를 읽지 못했다" >&2
            exit 1
        fi
        # 이름에 공백이 있어도 쪼개지지 않도록 줄 단위로 읽는다. 서브모듈 안의 명령(ssh 등)이
        # 반복문의 입력을 먹지 않도록 setup_submodule에는 빈 입력을 준다.
        while IFS= read -r key; do
            [ -n "$key" ] || continue
            name=${key#submodule.}
            name=${name%.path}
            path=$(git config -f .gitmodules --get "$key")
            if ! setup_submodule "$name" "$path" </dev/null; then
                echo "오류: $path: 서브모듈을 설정하지 못했다" >&2
                failed="$failed $path"
            else
                # 최신화할 지식 저장소: `projects/<이름>/`에 초기화되어 있고 온톨로지 층이 있다. 줄바꿈으로 구분해 이름에 공백이 있어도 쪼개지지 않게 한다.
                case $path in
                    projects/.*|projects/*/*) ;;
                    projects/*)
                        if [ -e "$path/.git" ] && [ -f "$path/docs/ontology/ontology.yaml" ]; then
                            knowledge="$knowledge${path#projects/}$nl"
                        fi
                        ;;
                esac
            fi
        done <<EOF
    $keys
    EOF
    fi

    # --- 복사된 기능의 최신화 ---
    # 서브모듈 설정이 일부 실패했어도 설정된 저장소는 최신화한다. 최신화가 실패해도 위의 결과는 그대로이고, 실패한 저장소는 끝에 알린다.
    sync_failed=""
    if [ -n "$knowledge" ]; then
        while IFS= read -r repo_name; do
            [ -n "$repo_name" ] || continue
            echo "projects/$repo_name: 복사된 기능을 최신화한다(just onto sync $repo_name)"
            if ! "{{just_executable()}}" --justfile "{{justfile()}}" onto sync "$repo_name" </dev/null; then
                sync_failed="$sync_failed $repo_name"
            fi
        done <<EOF
    $knowledge
    EOF
    fi

    status=0
    if [ -n "$failed" ]; then
        echo "설정하지 못한 서브모듈이 있습니다:$failed" >&2
        status=1
    fi
    if [ -n "$sync_failed" ]; then
        echo "최신화하지 못한 지식 저장소가 있습니다:$sync_failed. 이유는 위의 출력에 있습니다. 고친 뒤 \`just onto sync <이름>\`을 실행하세요" >&2
        status=1
    fi
    exit "$status"
