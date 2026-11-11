import BrandLoading from "../BrandLoading";
import styles from "./PageLoading.module.less";

/** Suspense fallback for lazy route chunks: the shared brand lockup. */
export default function PageLoading() {
  return (
    <div className={styles.host}>
      <BrandLoading />
    </div>
  );
}
