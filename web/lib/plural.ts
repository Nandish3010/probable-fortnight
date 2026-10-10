/** "1 gap", "2 gaps": only the word, the caller prints the number. */
export function plural(n: number, word: string): string {
  return n === 1 ? word : `${word}s`;
}
