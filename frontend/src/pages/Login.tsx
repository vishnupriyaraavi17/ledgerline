import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  ShieldCheck,
  Lock,
  User,
  Mail,
  Eye,
  EyeOff,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Shield,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiService } from '../services/api';

export const Login: React.FC = () => {
  const { login, error: authError, clearError, isAuthenticated, isLoading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Mode: 'login' | 'register'
  const [mode, setMode] = useState<'login' | 'register'>('login');

  // Login form state
  const [usernameOrEmail, setUsernameOrEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [isLoggingIn, setIsLoggingIn] = useState(false);

  // Registration form state
  const [regUsername, setRegUsername] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regPassword, setRegPassword] = useState('');
  const [regConfirmPassword, setRegConfirmPassword] = useState('');
  const [showRegPassword, setShowRegPassword] = useState(false);
  const [isRegistering, setIsRegistering] = useState(false);
  const [regError, setRegError] = useState<string | null>(null);
  const [regSuccess, setRegSuccess] = useState<string | null>(null);

  // If already authenticated, redirect to destination or home
  const from = (location.state as any)?.from?.pathname || '/';

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      navigate(from, { replace: true });
    }
  }, [isAuthenticated, isLoading, navigate, from]);

  // Clean up all sensitive form state upon component unmount or route transition
  useEffect(() => {
    return () => {
      setUsernameOrEmail('');
      setLoginPassword('');
      setRegUsername('');
      setRegEmail('');
      setRegPassword('');
      setRegConfirmPassword('');
      clearError();
    };
  }, [clearError]);

  const handleSwitchToLogin = () => {
    setMode('login');
    // Clear registration fields and errors
    setRegUsername('');
    setRegEmail('');
    setRegPassword('');
    setRegConfirmPassword('');
    setShowRegPassword(false);
    setRegError(null);
    clearError();
  };

  const handleSwitchToRegister = () => {
    setMode('register');
    // Clear login fields and errors
    setUsernameOrEmail('');
    setLoginPassword('');
    setShowLoginPassword(false);
    setRegSuccess(null);
    setRegError(null);
    clearError();
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameOrEmail || !loginPassword) return;

    setIsLoggingIn(true);
    try {
      await login({ username_or_email: usernameOrEmail, password: loginPassword });
      // Clear form on successful login
      setUsernameOrEmail('');
      setLoginPassword('');
      navigate(from, { replace: true });
    } catch {
      // Clear password field immediately upon failed login attempt
      setLoginPassword('');
    } finally {
      setIsLoggingIn(false);
    }
  };

  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setRegError(null);

    if (regPassword !== regConfirmPassword) {
      setRegError('Passwords do not match. Please verify both fields.');
      setRegPassword('');
      setRegConfirmPassword('');
      return;
    }

    if (regPassword.length < 8) {
      setRegError('Password must be at least 8 characters long.');
      setRegPassword('');
      setRegConfirmPassword('');
      return;
    }

    setIsRegistering(true);
    try {
      await apiService.register({
        username: regUsername.trim(),
        email: regEmail.trim(),
        password: regPassword,
      });

      // Clear all registration fields upon success and transition cleanly to sign in
      setRegUsername('');
      setRegEmail('');
      setRegPassword('');
      setRegConfirmPassword('');
      setRegSuccess('Your Account Holder profile has been registered. Please sign in below.');
      setMode('login');
    } catch (err: any) {
      // Clear sensitive password inputs on failure
      setRegPassword('');
      setRegConfirmPassword('');
      const detail = err.response?.data?.detail;
      setRegError(typeof detail === 'string' ? detail : 'Unable to complete registration. Please check the information provided.');
    } finally {
      setIsRegistering(false);
    }
  };

  const handleDevQuickSelect = (identifier: string) => {
    clearError();
    setUsernameOrEmail(identifier);
    setLoginPassword('');
  };

  return (
    <div className="min-h-screen bg-[#F6F7F4] flex flex-col lg:flex-row font-sans">
      {/* Left Brand & Visual Hero (Forest Green) */}
      <div className="lg:w-1/2 bg-[#102F28] text-white p-8 sm:p-12 lg:p-16 flex flex-col justify-between relative overflow-hidden">
        {/* Subtle decorative glow */}
        <div className="absolute top-0 right-0 w-96 h-96 bg-[#16382C] rounded-full filter blur-3xl opacity-40 pointer-events-none -mr-20 -mt-20" />
        <div className="absolute bottom-0 left-0 w-80 h-80 bg-[#1F5244] rounded-full filter blur-3xl opacity-30 pointer-events-none -ml-20 -mb-20" />

        {/* Top Brand Mark */}
        <div className="relative z-10 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-[#16382C] border border-[#2A6857]/40 flex items-center justify-center text-white shadow-sm">
            <ShieldCheck className="h-6 w-6 text-[#8BC7AE]" />
          </div>
          <div>
            <span className="text-xl font-serif font-bold tracking-tight text-[#F6F7F4]">LedgerLine</span>
          </div>
        </div>

        {/* Center Headline & Graphic */}
        <div className="relative z-10 my-12 lg:my-auto max-w-lg">
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-serif font-semibold tracking-tight leading-tight text-[#F6F7F4]">
            Your money. Your accounts. Your clarity.
          </h1>
          <p className="mt-3 text-base sm:text-lg font-serif italic text-[#8BC7AE]">
            Banking made simple, secure and transparent.
          </p>
          <p className="mt-4 text-sm sm:text-base text-[#D8E2DC]/85 leading-relaxed font-normal">
            Manage your accounts, move money between them and keep track of every transaction with confidence.
          </p>

          {/* Trust Indicators */}
          <div className="mt-8 p-6 rounded-2xl bg-[#0B231D]/60 border border-[#2A6857]/30 backdrop-blur-xs">
            <div className="flex items-center justify-between pb-4 border-b border-[#2A6857]/20">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#8BC7AE] animate-pulse" />
                <span className="text-xs font-medium text-[#D8E2DC]/90">INR &middot; Virtual Banking</span>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-4 text-left">
              <div>
                <span className="text-xs font-semibold text-[#F6F7F4] block">Secure Transactions</span>
                <span className="text-[11px] text-[#D8E2DC]/75 block mt-0.5">Verified financial operations</span>
              </div>
              <div>
                <span className="text-xs font-semibold text-[#F6F7F4] block">Transparent Records</span>
                <span className="text-[11px] text-[#D8E2DC]/75 block mt-0.5">Traceable transaction history</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Institutional Assurance */}
        <div className="relative z-10 pt-6 border-t border-[#2A6857]/30 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-[#D8E2DC]/70">
          <span>&copy; 2026 LedgerLine</span>
          <span className="flex items-center gap-1.5">
            <Shield className="w-3.5 h-3.5 text-[#8BC7AE]" />
            INR &middot; Virtual Banking
          </span>
        </div>
      </div>

      {/* Right Form Panel (Cream Canvas) */}
      <div className="lg:w-1/2 p-6 sm:p-12 lg:p-16 flex items-center justify-center">
        <div className="w-full max-w-md">
          {/* Card Surface */}
          <div className="bg-white rounded-2xl border border-[#E8EBE6] p-8 shadow-xs">
            {/* Mode Switcher Tabs */}
            <div className="flex rounded-xl bg-[#F6F7F4] p-1 mb-8 border border-[#E5EBE4]">
              <button
                type="button"
                onClick={handleSwitchToLogin}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition ${
                  mode === 'login'
                    ? 'bg-white text-[#1D2B27] shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27]'
                }`}
              >
                Sign In
              </button>
              <button
                type="button"
                onClick={handleSwitchToRegister}
                className={`flex-1 py-2 text-xs font-semibold rounded-lg transition ${
                  mode === 'register'
                    ? 'bg-white text-[#1D2B27] shadow-xs'
                    : 'text-[#6D7C73] hover:text-[#1D2B27]'
                }`}
              >
                Open an Account
              </button>
            </div>

            {/* Success Alert Banner */}
            {regSuccess && (
              <div className="mb-6 p-3.5 rounded-xl bg-[#EDF4ED] border border-[#E5EBE4] flex items-start gap-2.5 text-[#38724C] text-xs">
                <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="font-medium">{regSuccess}</div>
              </div>
            )}

            {/* Error Alert Banner */}
            {(authError || regError) && (
              <div className="mb-6 p-3.5 rounded-xl bg-[#FCF1E8] border border-[#F0DCD2] flex items-start gap-2.5 text-[#854B35] text-xs">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="font-medium">
                  {authError || regError}
                </div>
              </div>
            )}

            {mode === 'login' ? (
              /* SIGN IN FORM */
              <form onSubmit={handleLoginSubmit} className="space-y-5">
                <div>
                  <h2 className="text-2xl font-serif font-bold text-[#1D2B27]">Welcome back</h2>
                  <p className="mt-1 text-xs text-[#6D7C73]">
                    Sign in to access your accounts and financial ledger.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1.5">
                    Username or Email
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type="text"
                      autoComplete="username"
                      value={usernameOrEmail}
                      onChange={(e) => {
                        clearError();
                        setUsernameOrEmail(e.target.value);
                      }}
                      required
                      placeholder="e.g. holder or customer@example.com"
                      className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1.5">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type={showLoginPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      value={loginPassword}
                      onChange={(e) => {
                        clearError();
                        setLoginPassword(e.target.value);
                      }}
                      required
                      placeholder="••••••••••••"
                      className="w-full pl-10 pr-10 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowLoginPassword(!showLoginPassword)}
                      className="absolute right-3 top-2.5 text-[#89938E] hover:text-[#1D2B27] p-1 rounded-md transition"
                      title={showLoginPassword ? 'Hide password' : 'Show password'}
                    >
                      {showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isLoggingIn || !usernameOrEmail || !loginPassword}
                  className="w-full py-3 px-4 rounded-xl bg-[#102F28] hover:bg-[#16382C] disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 transition shadow-xs cursor-pointer"
                >
                  {isLoggingIn ? (
                    <span>Verifying credentials...</span>
                  ) : (
                    <>
                      <span>Sign In</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </form>
            ) : (
              /* REGISTRATION FORM (ACCOUNT HOLDERS ONLY) */
              <form onSubmit={handleRegisterSubmit} className="space-y-4">
                <div>
                  <h2 className="text-2xl font-serif font-bold text-[#1D2B27]">Open an Account</h2>
                  <p className="mt-1 text-xs text-[#6D7C73]">
                    Create a personal Account Holder profile. Accounts are initialized securely with ₹0.00 balance.
                  </p>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                    Username
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type="text"
                      autoComplete="username"
                      value={regUsername}
                      onChange={(e) => {
                        setRegError(null);
                        setRegUsername(e.target.value);
                      }}
                      required
                      minLength={3}
                      maxLength={64}
                      placeholder="e.g. rajesh_kumar"
                      className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                  </div>
                  <span className="text-[10px] text-[#89938E] mt-0.5 block">Alphanumeric, underscores, or hyphens (3–64 characters)</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                    Email Address
                  </label>
                  <div className="relative">
                    <Mail className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type="email"
                      autoComplete="email"
                      value={regEmail}
                      onChange={(e) => {
                        setRegError(null);
                        setRegEmail(e.target.value);
                      }}
                      required
                      placeholder="e.g. rajesh@example.com"
                      className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type={showRegPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={regPassword}
                      onChange={(e) => {
                        setRegError(null);
                        setRegPassword(e.target.value);
                      }}
                      required
                      minLength={8}
                      placeholder="At least 8 characters with letters & numbers"
                      className="w-full pl-10 pr-10 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowRegPassword(!showRegPassword)}
                      className="absolute right-3 top-2.5 text-[#89938E] hover:text-[#1D2B27] p-1 rounded-md transition"
                      title={showRegPassword ? 'Hide password' : 'Show password'}
                    >
                      {showRegPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-[#1D2B27] uppercase tracking-wider mb-1">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <Lock className="w-4 h-4 text-[#89938E] absolute left-3.5 top-3 pointer-events-none" />
                    <input
                      type={showRegPassword ? 'text' : 'password'}
                      autoComplete="new-password"
                      value={regConfirmPassword}
                      onChange={(e) => {
                        setRegError(null);
                        setRegConfirmPassword(e.target.value);
                      }}
                      required
                      minLength={8}
                      placeholder="Re-enter your password"
                      className="w-full pl-10 pr-3.5 py-2.5 text-sm bg-[#F6F7F4] border border-[#E8EBE6] rounded-xl focus:outline-none focus:ring-2 focus:ring-[#102F28] focus:bg-white transition text-[#1D2B27]"
                    />
                  </div>
                </div>

                <div className="p-3 rounded-xl bg-[#F6F7F4] border border-[#E8EBE6] text-[11px] text-[#6D7C73] leading-relaxed">
                  <span className="font-semibold text-[#1D2B27] block mb-0.5">Account Governance</span>
                  Public registration assigns the Account Holder role. Administrator and Auditor access require institution provisioning.
                </div>

                <button
                  type="submit"
                  disabled={isRegistering || !regUsername || !regEmail || !regPassword || !regConfirmPassword}
                  className="w-full py-3 px-4 rounded-xl bg-[#102F28] hover:bg-[#16382C] disabled:opacity-50 text-white text-sm font-semibold flex items-center justify-center gap-2 transition shadow-xs cursor-pointer mt-2"
                >
                  {isRegistering ? (
                    <span>Registering profile...</span>
                  ) : (
                    <>
                      <span>Complete Registration</span>
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </form>
            )}

            {/* Safe Local Development Identifier Helper (Zero Password Exposure) */}
            {DevIdentifierSelector && <DevIdentifierSelector onSelect={handleDevQuickSelect} />}
          </div>
        </div>
      </div>
    </div>
  );
};

/**
 * Local development account selector:
 * Only populates user identifiers into the username input.
 * Strips out completely from production builds via import.meta.env.DEV dead-code elimination.
 * Contains ZERO plaintext passwords or secrets.
 */
const DevIdentifierSelector = import.meta.env.DEV
  ? ({ onSelect }: { onSelect: (identifier: string) => void }) => {
      return (
        <div className="mt-8 pt-6 border-t border-[#E8EBE6]">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-[10px] font-semibold text-[#89938E] uppercase tracking-wider">
              Local Dev Profiles
            </span>
            <span className="text-[9px] bg-[#EDF4ED] text-[#38724C] px-1.5 py-0.5 rounded border border-[#E5EBE4] font-mono">
              Dev Only
            </span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => onSelect('admin')}
              className="p-2 text-left rounded-lg border border-[#E8EBE6] hover:border-[#102F28] hover:bg-[#F6F7F4] transition cursor-pointer"
            >
              <div className="text-xs font-bold text-[#1D2B27]">admin</div>
              <div className="text-[9px] text-[#6D7C73]">Administrator</div>
            </button>

            <button
              type="button"
              onClick={() => onSelect('holder')}
              className="p-2 text-left rounded-lg border border-[#E8EBE6] hover:border-[#102F28] hover:bg-[#F6F7F4] transition cursor-pointer"
            >
              <div className="text-xs font-bold text-[#1D2B27]">holder</div>
              <div className="text-[9px] text-[#6D7C73]">Account Holder</div>
            </button>

            <button
              type="button"
              onClick={() => onSelect('auditor')}
              className="p-2 text-left rounded-lg border border-[#E8EBE6] hover:border-[#102F28] hover:bg-[#F6F7F4] transition cursor-pointer"
            >
              <div className="text-xs font-bold text-[#1D2B27]">auditor</div>
              <div className="text-[9px] text-[#6D7C73]">Auditor (Read)</div>
            </button>
          </div>
          <span className="text-[10px] text-[#89938E] mt-1.5 block italic text-center">
            Populates username identifier. Enter your password to sign in.
          </span>
        </div>
      );
    }
  : null;
