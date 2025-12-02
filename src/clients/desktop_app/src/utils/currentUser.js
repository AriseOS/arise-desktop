/**
 * Current User Utility
 * Provides access to the currently logged-in user's information
 */

import { auth } from './auth';

/**
 * Get current user ID (username)
 *
 * @returns {Promise<string>} Current user's username
 * @throws {Error} If user is not logged in
 */
export async function getCurrentUserId() {
  const session = await auth.getSession();
  if (!session || !session.username) {
    throw new Error('User not logged in');
  }
  return session.username;
}

/**
 * Get current user session
 *
 * @returns {Promise<object|null>} Current user session or null
 */
export async function getCurrentSession() {
  try {
    return await auth.getSession();
  } catch (error) {
    console.error('[CurrentUser] Failed to get session:', error);
    return null;
  }
}

/**
 * Ensure user is logged in, throw error if not
 *
 * @returns {Promise<object>} Current user session
 * @throws {Error} If user is not logged in
 */
export async function requireLogin() {
  const session = await auth.getSession();
  if (!session || !session.username) {
    throw new Error('User not logged in. Please login first.');
  }
  return session;
}
