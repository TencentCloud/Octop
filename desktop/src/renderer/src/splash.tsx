import logoDarkUrl from "./assets/logo_horizontal_dark.png";
import logoWhiteUrl from "./assets/logo_horizontal_white.png";
import { LinuxWindowControls } from "./linux-window-controls";
import { mount } from "./mount";
import "./base.less";
import styles from "./splash.module.less";

/**
 * Splash of the Early Window (§4). It owns no state: the main process loads the
 * Dashboard into this same window once ``/api/health`` is green, or replaces this
 * page with the failure Result.
 *
 * The sidecar can take ten seconds or more on a cold start, so the page has to
 * read as "working", not as "stuck on a blank screen": the horizontal lockup
 * above the shared arc and one line saying what is being waited on, plus the
 * build number at the bottom for support.
 *
 * 顶部 58px 的拖动热区由 base.less 提供，正文区域不参与窗口拖动。
 */
function Splash() {
  const version = new URLSearchParams(window.location.search).get("version");

  return (
    <main className={styles.splash} role="status" aria-live="polite">
      <LinuxWindowControls />
      <div className={styles.stack}>
        <img
          className={`${styles.logo} ${styles.logoLight}`}
          src={logoDarkUrl}
          alt="Octop"
          height={72}
        />
        <img
          className={`${styles.logo} ${styles.logoDark}`}
          src={logoWhiteUrl}
          alt="Octop"
          height={72}
        />
        <p className={styles.status}>
          <span className={styles.spinner} aria-hidden="true">
            <span className={styles.track} />
            <span className={styles.ring} />
          </span>
          正在启动服务…
        </p>
      </div>
      {version ? <p className={styles.version}>{version}</p> : null}
    </main>
  );
}

mount(<Splash />);
