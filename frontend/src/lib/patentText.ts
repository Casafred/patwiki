export function patentText(value: string): string {
  if (!/<\/?(?:claims?|claim-text|p|b|br)\b/i.test(value)) return value
  const doc = new DOMParser().parseFromString(value, 'text/html')
  doc.querySelectorAll('script, style').forEach(node => node.remove())
  doc.querySelectorAll('claim-text, p, br').forEach(node => node.prepend(doc.createTextNode('\n')))
  const claims = Array.from(doc.querySelectorAll('claim'))
  const clean = (text: string) => text.replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{3,}/g, '\n\n').trim()
  if (!claims.length) return clean(doc.body.textContent || '')
  return claims.map(node => {
    let text = clean(node.textContent || '')
    const number = node.getAttribute('num')?.replace(/^0+(?=\d)/, '')
    if (number && /^\d+$/.test(number)) {
      text = text.replace(new RegExp(`^(?:${number}\\s*[.、]\\s*)+`), '')
      text = `${number}. ${text}`
    }
    return text
  }).join('\n\n')
}
