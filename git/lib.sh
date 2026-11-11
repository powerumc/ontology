# git 모듈의 레시피가 함께 쓰는 셸 함수(POSIX sh). 레시피가 `. "<이 파일>"`로 읽어 쓴다. 이 파일만 실행하지는 않는다.
#
# - 루트 저장소에서 실행한다고 가정한다. 저장소는 경로로 가리킨다: 루트 저장소는 `.`, 지식 저장소는 `projects/<이름>`.
# - 여기 있는 함수는 읽기만 하고 원격에 접속하지 않는다. 받기(`pull`)와 푸시(`push`)처럼 바꾸는 일은 각 레시피가 한다.
# - 판정은 모든 저장소에 같은 기준을 쓴다. 미푸시·뒤처짐은 `origin`의 같은 이름 브랜치와 비교한다.
#   `push`가 현재 브랜치를 같은 이름의 원격 브랜치로 올리기 때문이다. 원격 정보는 마지막으로 받은(fetch) 시점의 것이다.
# - 함수는 변수를 돌려주지 않고 출력한다. 실패하면 0이 아닌 값을 돌려주므로 호출하는 쪽이 `|| …`로 처리한다.
# - 초기화되지 않은 서브모듈은 빈 디렉토리라 `git -C <경로>`가 위로 올라가 루트 저장소를 읽는다. 경로를 받는 함수는 이를
#   막으려고 먼저 repo_initialized를 확인하고, 초기화되지 않았으면 아무것도 읽지 않고 실패한다. 그래도 호출하는 쪽이
#   repo_initialized를 먼저 보고 "초기화되지 않음"을 따로 다루어야 한다(실패를 다른 실패와 구별할 수 없다).
# - 사용자의 git 설정(diff.renames, diff.ignoreSubmodules, log.diffMerges, log.showRoot 등)에 따라 결과가 달라지지 않도록, 읽는 명령은 필요한 옵션을 직접 준다.

NL=$(printf '\nx')
NL=${NL%x}
TAB=$(printf '\t')
export NL TAB

# 루트 저장소의 표시 이름. 지식 저장소는 경로를 그대로 쓴다.
ROOT_LABEL="루트 저장소"

# 첫 번째 비어 있지 않은 줄.
first_line() {
    printf '%s\n' "$1" | sed -n '/./{p;q;}'
}

# print_group <이름> <줄 목록>: 줄마다 `<이름>: <줄>`로 적는다. 목록이 비어 있으면 아무것도 적지 않는다.
print_group() {
    [ -n "$2" ] || return 0
    printf '%s' "$2" | while IFS= read -r pg_line; do
        printf '%s: %s\n' "$1" "$pg_line"
    done
}

# 등록된 지식 저장소를 한 줄에 하나씩 `<경로><탭><서브모듈 이름>`으로 적는다. 서브모듈 이름은 .gitmodules의 이름이다.
# 등록은 .gitmodules의 항목이고, 루트가 기록한 커밋(gitlink)이 없는 항목은 건너뛴다(`just setup`과 같은 기준).
# .gitmodules를 읽지 못하면 이유를 stderr에 적고 실패한다.
knowledge_repos() {
    [ -f .gitmodules ] || return 0
    kr_status=0
    # 종료 코드 1은 항목이 없다는 뜻이고, 그 밖은 .gitmodules를 읽지 못한 것이다(예: 충돌 표시가 남은 경우).
    kr_keys=$(git config -f .gitmodules --name-only --get-regexp '^submodule\..*\.path$') || kr_status=$?
    if [ "$kr_status" -gt 1 ]; then
        echo "오류: .gitmodules를 읽지 못했다" >&2
        return 1
    fi
    # 이름에 공백이 있어도 쪼개지지 않도록 줄 단위로 읽는다.
    while IFS= read -r kr_key; do
        [ -n "$kr_key" ] || continue
        kr_name=${kr_key#submodule.}
        kr_name=${kr_name%.path}
        kr_path=$(git config -f .gitmodules --get "$kr_key")
        kr_mode=$(git --literal-pathspecs ls-files --stage -- "$kr_path" | cut -c1-6)
        if [ "$kr_mode" != "160000" ]; then
            echo "주의: $kr_path: .gitmodules에는 있지만 루트에 기록된 커밋이 없어 건너뛰었다" >&2
            continue
        fi
        printf '%s\t%s\n' "$kr_path" "$kr_name"
    done <<EOF
$kr_keys
EOF
}

# 지식 저장소(서브모듈 이름 $1, 경로 $2)의 추적 브랜치. .gitmodules에 기록된 것, 없으면 원격의 기본 브랜치. 모르면 아무것도 적지 않는다.
tracking_branch() {
    tb_branch=$(git config -f .gitmodules --get "submodule.$1.branch" || true)
    if [ -z "$tb_branch" ]; then
        repo_initialized "$2" || return 1
        tb_branch=$(git -C "$2" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || true)
        tb_branch=${tb_branch#origin/}
    fi
    printf '%s\n' "$tb_branch"
}

# 서브모듈이 초기화되어(작업 트리에 .git이 있어) 쓸 수 있는가.
repo_initialized() {
    [ "$1" = . ] || [ -e "$1/.git" ]
}

# 현재 브랜치 이름. detached HEAD이면 아무것도 적지 않는다.
repo_branch() {
    repo_initialized "$1" || return 1
    git -C "$1" symbolic-ref --quiet --short HEAD 2>/dev/null || true
}

# 미커밋 변경을 `git status --porcelain` 줄로 적는다(추적하지 않는 파일 포함, 무시되는 파일 제외).
# 서브모듈 안의 변경은 그 저장소 쪽에서 센다. 여기서는 서브모듈 포인터(새 커밋)가 달라진 것만 변경으로 본다.
# 이름을 바꾼 파일은 옛 경로의 삭제와 새 경로의 추가로 적는다(--no-renames). 탐지 설정(status.renames, diff.renames)에 따라 줄 수가 달라지지 않게 한다.
repo_changes() {
    repo_initialized "$1" || return 1
    GIT_OPTIONAL_LOCKS=0 git -C "$1" -c core.quotePath=false status --porcelain --untracked-files=all --ignore-submodules=dirty --no-renames
}

# 원격(origin)에 브랜치 $2가 있는가. 마지막으로 받은 원격 정보 기준이다.
repo_has_remote_branch() {
    repo_initialized "$1" || return 1
    git -C "$1" rev-parse --verify --quiet "refs/remotes/origin/$2" >/dev/null 2>&1
}

# 푸시하지 않은 커밋 수. 브랜치 $2가 원격에 있으면 origin/$2 이후의 커밋, 없으면(새 작업 브랜치, detached HEAD)
# origin의 어느 브랜치에도 없는 커밋이다. $2가 비어 있으면 detached HEAD로 본다.
repo_unpushed_count() {
    repo_initialized "$1" || return 1
    if [ -n "${2:-}" ] && repo_has_remote_branch "$1" "$2"; then
        git -C "$1" rev-list --count "refs/remotes/origin/$2..HEAD"
    else
        git -C "$1" rev-list --count HEAD --not --remotes=origin
    fi
}

# 원격보다 뒤처진 커밋 수: origin/$2에는 있고 HEAD에는 없는 커밋. 브랜치가 원격에 없으면 실패한다.
repo_behind_count() {
    repo_initialized "$1" || return 1
    repo_has_remote_branch "$1" "$2" || return 1
    git -C "$1" rev-list --count "HEAD..refs/remotes/origin/$2"
}

# 루트 저장소에서 서브모듈 포인터가 바뀌었으나 커밋하지 않은 경로를 한 줄에 하나씩 적는다.
# 스테이징한 것(등록·제거·옮기기 포함)과 하지 않은 것(서브모듈이 새 커밋으로 올라간 것)을 모두 적는다.
# 옮긴 서브모듈은 옛 경로(제거)와 새 경로(추가)를 따로 적는다. 이름 바꾸기 탐지를 끄므로 diff.renames 설정과 무관하다.
# `git diff`는 인덱스를 새로 쓰므로(GIT_OPTIONAL_LOCKS=0도 소용없다) 인덱스를 읽기만 하는 diff-files와 diff-index를 쓴다.
# HEAD가 아직 없으면(첫 커밋 전) 빈 트리와 비교한다.
pointer_changes() {
    pc_head=$(git rev-parse --verify --quiet HEAD || git hash-object -t tree /dev/null)
    {
        git -c core.quotePath=false diff-files --raw --no-renames --ignore-submodules=dirty 2>/dev/null || true
        git -c core.quotePath=false diff-index --cached --raw --no-renames --ignore-submodules=none "$pc_head" 2>/dev/null || true
    } | awk -F '\t' '$1 ~ /^:(160000 [0-7]+|[0-7]+ 160000) / { print $2 }' | sort -u
}

# 루트 저장소가 기록한 서브모듈 $1의 커밋과 실제로 체크아웃된 커밋이 다른가(스테이징하지 않은 포인터 변경). 서브모듈 안의 미커밋 변경은 보지 않는다.
pointer_changed() {
    ! git diff-files --quiet --ignore-submodules=dirty -- "$1"
}

# 루트 저장소의 커밋 $2(기본은 HEAD)가 경로 $1에 기록한 서브모듈 커밋을 적는다. 그 커밋에 서브모듈 기록이 없으면(커밋 전의
# 등록, 첫 커밋 전, 없는 브랜치) 실패한다.
recorded_commit() {
    rcm_line=$(git --literal-pathspecs ls-tree "${2:-HEAD}" -- "$1" 2>/dev/null) || return 1
    # 출력은 "<모드> <종류> <해시><탭><경로>"이고, 서브모듈은 160000 commit이다.
    case $rcm_line in
        "160000 commit "*) ;;
        *) return 1 ;;
    esac
    rcm_rest=${rcm_line#160000 commit }
    printf '%s\n' "${rcm_rest%%"$TAB"*}"
}

# 지식 저장소 $1의 origin 브랜치 어디에든 커밋 $2가 있는가. 마지막으로 받거나 푸시한 원격 정보 기준이고 원격에 접속하지 않는다.
# 저장소에 그 커밋이 아예 없어도(for-each-ref가 실패한다) 원격에 없는 것이다.
repo_has_remote_commit() {
    repo_initialized "$1" || return 1
    rhc_refs=$(git -C "$1" for-each-ref --contains "$2" --format='%(refname)' refs/remotes/origin 2>/dev/null) || return 1
    [ -n "$rhc_refs" ]
}

# 이번 푸시로 루트 저장소의 원격에 올라가는 커밋들이 가리키는 서브모듈 커밋 가운데, 원격에 있다고 확인되지 않는 것을
# `<경로> <짧은 해시> (<기록한 루트 커밋과 이유, 할 일>)`로 한 줄에 하나씩 적는다. 푸시하면 원격의 루트 저장소가 원격에 없는 커밋을
# 가리키게 되는 곳을 찾는 것이다. $1은 루트 저장소의 현재 브랜치다. 올라가는 커밋을 읽지 못하면 실패한다.
# - 무엇을 볼지는 올라가는 커밋이 정한다. 작업 트리의 .gitmodules나 인덱스 같은 미커밋 상태는 보지 않는다. 올라가는 커밋은
#   origin/$1 이후의 것이고, 원격에 그 브랜치가 없으면(새 작업 브랜치) origin의 어느 브랜치에도 없는 커밋이다(repo_unpushed_count와 같다).
#   HEAD뿐 아니라 함께 올라가는 중간 커밋도 보는 것은, 받는 사람이 그 커밋을 체크아웃해도 서브모듈을 받을 수 있어야 해서다.
# - 그 커밋들이 새로 기록하거나 바꾼 서브모듈 커밋만 본다. 같은 커밋을 여러 루트 커밋이 기록했으면 가장 먼저 기록한 것을 적는다.
# - 사용자 설정에 기대지 않는다. 옵션을 직접 주어 고정한다: --ignore-submodules=none(diff.ignoreSubmodules), --no-renames(diff.renames),
#   --diff-merges=separate(log.diffMerges: 병합 커밋을 부모마다 본다. 결합 형식이면 raw 줄의 열이 달라진다), --root(log.showRoot:
#   부모 없는 첫 커밋도 본다), --no-show-signature(log.showSignature: 서명 검증 출력이 섞이지 않게 한다).
# - 루트의 origin/$1이 이미 같은 경로에 같은 커밋을 기록하고 있으면 새로 알리는 것이 아니라서 넘어간다. 그 커밋을 로컬에 아직 받아 오지
#   않았거나 저장소를 초기화하지 않았어도 마찬가지다.
# - 그 경로에 초기화된 저장소가 있으면 그 저장소의 원격 추적 참조에 커밋이 있어야 한다. 마지막으로 받거나 푸시한 시점의 정보라서, 그 사이에
#   원격에 올라간 커밋은 없는 것으로 보고 거부하는 쪽으로 대개 틀린다(원격에서 지워진 브랜치의 추적 참조가 prune 전에 남은 경우는 반대로 틀린다).
# - 그 경로에 저장소가 없으면(초기화하지 않았거나 등록을 해제했다) 확인할 수 없는 것으로 적는다.
unpublished_pointers() {
    up_branch=$1
    # 원격에 같은 이름의 브랜치가 있으면 그 이후, 없으면 origin의 어느 브랜치에도 없는 커밋
    up_options="--format=%H --raw --no-renames --no-abbrev --ignore-submodules=none --diff-merges=separate --root --no-show-signature"
    if git rev-parse --verify --quiet "refs/remotes/origin/$up_branch" >/dev/null 2>&1; then
        # shellcheck disable=SC2086
        up_log=$(git -c core.quotePath=false log $up_options HEAD --not "refs/remotes/origin/$up_branch" 2>/dev/null) || return 1
    else
        # shellcheck disable=SC2086
        up_log=$(git -c core.quotePath=false log $up_options HEAD --not --remotes=origin 2>/dev/null) || return 1
    fi
    # 출력은 커밋마다(병합은 부모마다) "<커밋 해시>" 줄과 raw 줄들이다.
    # raw 줄: ":<옛 모드> <새 모드> <옛 해시> <새 해시> <상태><탭><경로>". 새 모드가 160000이면 서브모듈이 새 커밋으로 기록된 것이다.
    # 로그는 새 커밋부터 나오므로 같은 (경로, 커밋)을 여러 번 만나면 마지막(가장 먼저 기록한 루트 커밋)이 남는다.
    up_pairs=$(printf '%s\n' "$up_log" | awk -F '\t' '
        /^[0-9a-f]+$/ { commit = $0; next }
        /^:/ { split($1, m, " "); if (m[2] == "160000") found[$2 "\t" m[4]] = commit }
        END { for (key in found) print key "\t" found[key] }' | sort)
    while IFS="$TAB" read -r up_path up_sha up_commit; do
        [ -n "$up_path" ] || continue
        [ "$(recorded_commit "$up_path" "refs/remotes/origin/$up_branch")" != "$up_sha" ] || continue
        up_by="기록한 루트 커밋 $(printf %.7s "$up_commit")"
        if repo_initialized "$up_path"; then
            ! repo_has_remote_commit "$up_path" "$up_sha" || continue
            up_note=" ($up_by. 원격에 없다. 그 커밋을 지식 저장소의 원격에 올리거나 그 루트 커밋을 고쳐 쓰세요)"
        else
            up_note=" ($up_by. 초기화되지 않았거나 없어 확인할 수 없다. just setup으로 초기화하거나 그 루트 커밋을 고쳐 쓰세요)"
        fi
        printf '%s %s%s\n' "$up_path" "$(printf %.7s "$up_sha")" "$up_note"
    done <<EOF
$up_pairs
EOF
}
