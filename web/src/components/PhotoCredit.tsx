import type { LibraryImage } from "../api";

/** A library photo's title, author and licence. Photos used by permission
 * (tier 2) have no public page or licence link: those parts are plain text. */
export function PhotoCredit({ image }: { image: LibraryImage }) {
  return (
    <>
      {image.source.startsWith("http") ? (
        <a href={image.source} target="_blank" rel="noreferrer">
          {image.title}
        </a>
      ) : (
        image.title
      )}{" "}
      · {image.author} ·{" "}
      {image.licence_url ? (
        <a href={image.licence_url} target="_blank" rel="noreferrer">
          {image.licence}
        </a>
      ) : (
        image.licence
      )}
    </>
  );
}
