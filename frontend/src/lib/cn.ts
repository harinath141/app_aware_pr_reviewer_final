/** Join conditional class names. Small enough that a dependency would not earn its place. */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}
