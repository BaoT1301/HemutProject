import { useEffect } from "react";
import AmbientBackground from "./components/AmbientBackground";
import Header from "./components/Header";
import UploadCard from "./components/UploadCard";
import ProgressCard from "./components/ProgressCard";
import FooterGrid from "./components/FooterGrid";
import { useUpload } from "./hooks/useUpload";
import { useJobPolling } from "./hooks/useJobPolling";
import { getDownloadUrl } from "./lib/api";

export default function App() {
  const {
    file,
    email,
    isSubmitting,
    jobId,
    total,
    uploadError,
    setFile,
    setEmail,
    submit,
    stopSubmitting,
  } = useUpload();

  const { job, isComplete, isFailed } = useJobPolling(jobId);

  // Stop the submit spinner when job terminates
  useEffect(() => {
    if (isComplete || isFailed) {
      stopSubmitting();
    }
  }, [isComplete, isFailed, stopSubmitting]);

  const showProgress = jobId !== null || uploadError !== null;

  const handleDownload = () => {
    if (jobId) {
      window.location.href = getDownloadUrl(jobId);
    }
  };

  return (
    <>
      <AmbientBackground />
      <div className="page">
      <Header />
      <UploadCard
        file={file}
        email={email}
        isSubmitting={isSubmitting}
        onFileSelect={setFile}
        onFileClear={() => setFile(null)}
        onEmailChange={setEmail}
        onSubmit={submit}
      />
      {showProgress && (
        <ProgressCard
          job={job}
          total={total}
          isComplete={isComplete}
          isFailed={isFailed}
          uploadError={uploadError}
          onDownload={handleDownload}
        />
      )}
      <FooterGrid />
      </div>
    </>
  );
}
