/**
 * 本地规则：只有图标的按钮必须使用 <IconButton label=…>（悬停 / 聚焦时显示多语言提示）。
 *
 * 报告：
 * - <Button size='icon' | 'icon-*'>；
 * - 子节点只有元素（图标）、没有可见文本的 <Button>（sr-only 文本不算可见）。
 */
const isSrOnly = (el) =>
  el.openingElement.attributes.some(
    (a) =>
      a.type === 'JSXAttribute' &&
      a.name.name === 'className' &&
      a.value?.type === 'Literal' &&
      /\bsr-only\b/.test(String(a.value.value))
  )

/** 节点是否含可见文本。 */
function hasVisibleText(node) {
  switch (node.type) {
    case 'JSXText':
      return node.value.trim() !== ''
    case 'JSXElement':
      return !isSrOnly(node) && node.children.some(hasVisibleText)
    case 'JSXFragment':
      return node.children.some(hasVisibleText)
    case 'JSXExpressionContainer':
      return exprHasText(node.expression)
    default:
      return false
  }
}

function exprHasText(e) {
  switch (e.type) {
    case 'JSXEmptyExpression':
      return false
    case 'JSXElement':
    case 'JSXFragment':
      return hasVisibleText(e)
    case 'ConditionalExpression':
      return exprHasText(e.consequent) || exprHasText(e.alternate)
    case 'LogicalExpression':
      return exprHasText(e.right)
    case 'Literal':
      return e.value != null && e.value !== false && String(e.value) !== ''
    default:
      // 变量、函数调用、模板字符串等视为可能是文本
      return true
  }
}

export default {
  meta: {
    type: 'problem',
    docs: { description: 'icon-only buttons must use <IconButton label>' },
    messages: {
      useIconButton:
        '只有图标的按钮请使用 <IconButton label={…}>（提供悬停提示与 aria-label）',
    },
    schema: [],
  },
  create(context) {
    return {
      JSXElement(node) {
        const name = node.openingElement.name
        if (name.type !== 'JSXIdentifier' || name.name !== 'Button') return
        const size = node.openingElement.attributes.find(
          (a) => a.type === 'JSXAttribute' && a.name.name === 'size'
        )
        const iconSize =
          size?.value?.type === 'Literal' &&
          /^icon/.test(String(size.value.value))
        const children = node.children.filter(
          (c) => !(c.type === 'JSXText' && c.value.trim() === '')
        )
        const iconOnly =
          children.length > 0 && !children.some(hasVisibleText)
        if (iconSize || iconOnly)
          context.report({ node: node.openingElement, messageId: 'useIconButton' })
      },
    }
  },
}
