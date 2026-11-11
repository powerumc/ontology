# git 모듈의 레시피가 함께 쓰는 셸 함수(POSIX sh). 레시피가 `. "<이 파일>"`로 읽어 쓴다. 이 파일만 실행하지는 않는다.
#
# - 루트 저장소에서 실행한다고 가정한다. 저장소는 경로로 가리킨다: 루트 저장소는 `.`, 지식 저장소는 `projects/<이름>`.
# - 여기 있는 함수는 읽기만 하고 원격에 접속하지 않는다. 받기(`pull`)와 푸시(`push`)처럼 바꾸는 일은 각 레시피가 한다.
# - 판정은 모든 저장소에 같은 기준을 쓴다. 미푸시·뒤처짐은 `origin`의 같은 이름 브랜치와 비교한다.
#   `push`가 현재 브랜치를 같은 이름의 원격 브랜치로 올리기 때문이다. 원격 정보는 마지막으로 받은(fetch) 시점의 것이다.
# - 함수는 변수를 돌려주지 않고 출력한다. 실패하면 0이 아닌 값을 돌려주므로 호출하는 쪽이 `|| …`로 처리한다.

NL=$(printf '\nx')
NL=${NL%x}
TAB=$(printf '\t')
export NL TAB

# 루트 저장소의 표시 이름. 지식 저장소는 경로를 그대로 쓴다.
ROOT_LABEL="루트 저장소"

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
    git -C "$1" symbolic-ref --quiet --short HEAD 2>/dev/null || true
}

# 미커밋 변경을 `git status --porcelain` 줄로 적는다(추적하지 않는 파일 포함, 무시되는 파일 제외).
# 서브모듈 안의 변경은 그 저장소 쪽에서 센다. 여기서는 서브모듈 포인터(새 커밋)가 달라진 것만 변경으로 본다.
repo_changes() {
    GIT_OPTIONAL_LOCKS=0 git -C "$1" -c core.quotePath=false status --porcelain --untracked-files=all --ignore-submodules=dirty
}

# 원격(origin)에 브랜치 $2가 있는가. 마지막으로 받은 원격 정보 기준이다.
repo_has_remote_branch() {
    git -C "$1" rev-parse --verify --quiet "refs/remotes/origin/$2" >/dev/null 2>&1
}

# 푸시하지 않은 커밋 수. 브랜치 $2가 원격에 있으면 origin/$2 이후의 커밋, 없으면(새 작업 브랜치, detached HEAD)
# origin의 어느 브랜치에도 없는 커밋이다. $2가 비어 있으면 detached HEAD로 본다.
repo_unpushed_count() {
    if [ -n "${2:-}" ] && repo_has_remote_branch "$1" "$2"; then
        git -C "$1" rev-list --count "refs/remotes/origin/$2..HEAD"
    else
        git -C "$1" rev-list --count HEAD --not --remotes=origin
    fi
}

# 원격보다 뒤처진 커밋 수: origin/$2에는 있고 HEAD에는 없는 커밋. 브랜치가 원격에 없으면 실패한다.
repo_behind_count() {
    repo_has_remote_branch "$1" "$2" || return 1
    git -C "$1" rev-list --count "HEAD..refs/remotes/origin/$2"
}

# 루트 저장소에서 서브모듈 포인터가 바뀌었으나 커밋하지 않은 경로를 한 줄에 하나씩 적는다.
# 스테이징한 것(등록·제거 포함)과 하지 않은 것(서브모듈이 새 커밋으로 올라간 것)을 모두 적는다.
# `git diff`는 인덱스를 새로 쓰므로(GIT_OPTIONAL_LOCKS=0도 소용없다) 인덱스를 읽기만 하는 diff-files와 diff --cached를 쓴다.
pointer_changes() {
    {
        git -c core.quotePath=false diff-files --ignore-submodules=dirty --raw 2>/dev/null || true
        git -c core.quotePath=false diff --cached --raw 2>/dev/null || true
    } | awk -F '\t' '$1 ~ /^:(160000 [0-7]+|[0-7]+ 160000) / { print $2 }' | sort -u
}

# 루트 저장소가 기록한 서브모듈 $1의 커밋과 실제로 체크아웃된 커밋이 다른가(스테이징하지 않은 포인터 변경). 서브모듈 안의 미커밋 변경은 보지 않는다.
pointer_changed() {
    ! git diff-files --quiet --ignore-submodules=dirty -- "$1"
}
