#!/bin/bash
# ============================================================================
# i18n.sh — ALine 翻译工作流脚本
# ============================================================================
# 工作流: 提取(extract) → 合并(update) → 编译(compile)
#
# 依赖: Python 3 + Babel (pip install babel)
# 用法:
#   bash scripts/i18n.sh            # 完整流程: 提取 → 合并 → 编译
#   bash scripts/i18n.sh extract    # 仅提取 POT
#   bash scripts/i18n.sh merge      # 仅合并 .po
#   bash scripts/i18n.sh compile    # 仅编译 .mo
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

PYBABEL="${PYBABEL:-pybabel}"
LOCALE_DIR="locale"
DOMAIN="aline"
POT_FILE="${LOCALE_DIR}/${DOMAIN}.pot"
SOURCES=("core" "ui" "processing")
LOCALES=("zh_CN")

# --- helpers --------------------------------------------------------------
extract() {
    echo "🔍 [1/3] 提取字符串 → ${POT_FILE}"
    mkdir -p "${LOCALE_DIR}"
    $PYBABEL extract \
        --output="${POT_FILE}" \
        --project="ALine" \
        --version="0.3" \
        --copyright-holder="ALine" \
        --keyword="_" \
        --keyword="_n:1,2" \
        --charset="utf-8" \
        --no-wrap \
        "${SOURCES[@]}"

    local count
    count=$(grep -c "^msgid " "${POT_FILE}" 2>/dev/null || echo 0)
    echo "   ✅ POT 条目: $(( count - 1 )) (不含 header)"
}

merge() {
    echo "🔄 [2/3] 合并 → .po 文件"
    for locale in "${LOCALES[@]}"; do
        local po_file="${LOCALE_DIR}/${locale}/LC_MESSAGES/${DOMAIN}.po"
        if [ -f "${po_file}" ]; then
            echo "   📝 更新 ${locale} ..."
            $PYBABEL update \
                --input-file="${POT_FILE}" \
                --output-dir="${LOCALE_DIR}" \
                --locale="${locale}" \
                --domain="${DOMAIN}" \
                --init-missing \
                --no-wrap
        else
            echo "   🆕 初始化 ${locale} ..."
            $PYBABEL init \
                --input-file="${POT_FILE}" \
                --output-dir="${LOCALE_DIR}" \
                --locale="${locale}" \
                --domain="${DOMAIN}"
        fi

        local count
        count=$(grep -c "^msgid " "${po_file}" 2>/dev/null || echo 0)
        echo "   ✅ ${locale} PO 条目: $(( count - 1 ))"
    done
}

compile() {
    echo "⚙️  [3/3] 编译 → .mo 文件"
    for locale in "${LOCALES[@]}"; do
        local po_file="${LOCALE_DIR}/${locale}/LC_MESSAGES/${DOMAIN}.po"
        local mo_file="${LOCALE_DIR}/${locale}/LC_MESSAGES/${DOMAIN}.mo"

        if [ ! -f "${po_file}" ]; then
            echo "   ⚠️  跳过 ${locale} (.po 不存在)"
            continue
        fi

        echo "   🛠  编译 ${locale} ..."
        $PYBABEL compile \
            --directory="${LOCALE_DIR}" \
            --locale="${locale}" \
            --domain="${DOMAIN}" \
            --statistics

        if [ -f "${mo_file}" ]; then
            local size
            size=$(stat --printf="%s" "${mo_file}" 2>/dev/null || stat -f%z "${mo_file}" 2>/dev/null)
            echo "   ✅ ${locale} → ${mo_file} (${size} bytes)"
        fi
    done
}

summary() {
    echo ""
    echo "═══════════════════════════════════════════"
    echo " 📊 i18n: 更新完成"
    echo "═══════════════════════════════════════════"
    if [ -f "${POT_FILE}" ]; then
        local pot_count
        pot_count=$(grep -c "^msgid " "${POT_FILE}" 2>/dev/null || echo 0)
        echo "   POT: $(( pot_count - 1 )) 条目"
    fi
    for locale in "${LOCALES[@]}"; do
        local po_file="${LOCALE_DIR}/${locale}/LC_MESSAGES/${DOMAIN}.po"
        local mo_file="${LOCALE_DIR}/${locale}/LC_MESSAGES/${DOMAIN}.mo"
        if [ -f "${po_file}" ]; then
            local po_count
            po_count=$(grep -c "^msgid " "${po_file}" 2>/dev/null || echo 0)
            echo "   ${locale} PO: $(( po_count - 1 )) 条目"
        fi
        if [ -f "${mo_file}" ]; then
            local mo_size
            mo_size=$(stat --printf="%s" "${mo_file}" 2>/dev/null || stat -f%z "${mo_file}" 2>/dev/null)
            echo "   ${locale} MO: ${mo_size} bytes"
        fi
    done
    echo "═══════════════════════════════════════════"
}

# --- main -----------------------------------------------------------------
case "${1:-all}" in
    extract)
        extract
        ;;
    merge|update)
        merge
        ;;
    compile)
        compile
        ;;
    all|"")
        extract
        merge
        compile
        summary
        ;;
    *)
        echo "用法: $0 {extract|merge|compile|all}"
        echo "  extract   仅提取 POT（从源码扫描 _() 调用）"
        echo "  merge     将 POT 合并到现有 .po 文件"
        echo "  compile   将 .po 编译为 .mo"
        echo "  all       完整流程 (默认)"
        exit 1
        ;;
esac
