import markUrl from "./assets/octop-mark.svg";
import { mount } from "./mount";
import "./base.css";
import "./splash.css";

/**
 * Splash of the Early Window (§4). It owns no state: the main process swaps the
 * whole window for the Dashboard once ``/api/health`` is green, or replaces this
 * page with the failure Result.
 */
function Splash() {
  return (
    <>
      <div className="shell-drag-strip" aria-hidden="true" />
      <main className="splash" role="status" aria-live="polite">
        <div className="splash__mark" aria-hidden="true">
          <span className="splash__ring" />
          <img className="splash__logo" src={markUrl} alt="" width={60} height={60} />
        </div>
        <p className="splash__text">正在启动 Octop…</p>
      </main>
    </>
  );
}

mount(<Splash />);
