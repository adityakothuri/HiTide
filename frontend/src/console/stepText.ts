const ACT_WORD: Record<string, string> = { sms: 'Texted', poll: 'Sent a safe/help poll', voice: 'Called', open_case: 'Opened a case', spoken: 'Spoke an alert in the app', parent: 'Copied the parent' }

const cap = (x: string) => x.charAt(0).toUpperCase() + x.slice(1)

/**
 * One outreach timeline entry in plain words.
 * "danger -> voice:danger_call" becomes "Called (danger)";
 * "HELP from driver -> responders flagged" becomes "Asked for help · responders flagged".
 */
export function stepText(what: string): string {
  const help = /^HELP from (\w+) -> (.+)$/.exec(what)
  if (help) {
    const [, by, rest] = help
    return `${by === 'driver' ? 'Asked for help' : `${cap(by)} asked for help`} · ${rest}`
  }
  const m = /^(\w+) -> (.+)$/.exec(what)
  if (!m) return cap(what)
  const [, level, acts] = m
  const words = acts.split(',').map((a) => {
    const kind = a.trim().split(':')[0]
    return ACT_WORD[kind] ?? kind
  })
  return `${words.join(', ')} (${level})`
}
