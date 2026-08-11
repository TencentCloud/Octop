/** Client-side mirror of ``octop.infra.users.password.validate_password_policy``. */

export const MIN_PASSWORD_LENGTH = 8;

const COMMON_PASSWORDS = new Set([
  "password",
  "password1",
  "password12",
  "password123",
  "12345678",
  "123456789",
  "qwerty123",
  "admin123",
  "welcome1",
  "letmein1",
  "changeme1",
  "octop123",
  "abc12345",
  "iloveyou1",
]);

export type PasswordPolicyIssue =
  | "same_as_old"
  | "too_short"
  | "need_letter_and_digit"
  | "too_common";

/** Return the first policy violation, or null when acceptable. */
export function passwordPolicyIssue(
  password: string,
  oldPassword?: string,
): PasswordPolicyIssue | null {
  if (oldPassword !== undefined && password === oldPassword) {
    return "same_as_old";
  }
  if (password.length < MIN_PASSWORD_LENGTH) {
    return "too_short";
  }
  const hasLetter = /\p{L}/u.test(password);
  const hasDigit = /\p{N}/u.test(password);
  if (!hasLetter || !hasDigit) {
    return "need_letter_and_digit";
  }
  if (COMMON_PASSWORDS.has(password.toLowerCase())) {
    return "too_common";
  }
  return null;
}
