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
    # 서브모듈 순회(knowledge_repos), 추적 브랜치(tracking_branch), 기록한 커밋(indexed_commit)은 git 모듈과 같은 함수를 쓴다.
    . "{{source_directory()}}/git/lib.sh"

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

        # 루트가 기록한 커밋. `knowledge_repos`가 기록이 있는 항목만 주므로 있다. 스테이징만 한 등록(`just repo add`)의 것도 인덱스에서 읽는다.
        recorded=$(indexed_commit "$path") || return 1

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
        branch=$(tracking_branch "$name" "$path" || true)
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
    # 등록된 서브모듈을 한 줄에 `<경로><탭><서브모듈 이름>`으로 받는다. 이름에 공백이 있어도 쪼개지지 않는다. .gitmodules를 읽지 못하면
    # `knowledge_repos`가 이유를 알리고, 루트가 기록한 커밋이 없는 항목은 알린 뒤 건너뛴다. 서브모듈 안의 명령(ssh 등)이 반복문의 입력을
    # 먹지 않도록 setup_submodule에는 빈 입력을 준다.
    if ! repos=$(knowledge_repos </dev/null); then
        exit 1
    fi
    while IFS="$TAB" read -r path name; do
        [ -n "$path" ] || continue
        if ! setup_submodule "$name" "$path" </dev/null; then
            echo "오류: $path: 서브모듈을 설정하지 못했다" >&2
            failed="$failed $path"
        else
            # 최신화할 지식 저장소: `projects/<이름>/`에 초기화되어 있고 온톨로지 층이 있다. 줄바꿈으로 구분해 이름에 공백이 있어도 쪼개지지 않게 한다.
            case $path in
                projects/.*|projects/*/*) ;;
                projects/*)
                    if [ -e "$path/.git" ] && [ -f "$path/docs/ontology/ontology.yaml" ]; then
                        knowledge="$knowledge${path#projects/}$NL"
                    fi
                    ;;
            esac
        fi
    done <<EOF
    $repos
    EOF

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
