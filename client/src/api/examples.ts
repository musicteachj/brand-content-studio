import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BrandProfile, DocumentFormat, ExampleBrand, ExamplesResponse } from "@/types";

/** GET /api/examples: public, no sign-in. The server caches it for 60 s, so do we. */
export const examplesQuery = {
  queryKey: ["examples"],
  queryFn: async () => (await api.get<ExamplesResponse>("/examples")).data,
  staleTime: 60_000,
};

export function useExamples() {
  return useQuery(examplesQuery);
}

/** An example document's public download URL (no sign-in), relative to the API base. */
export function exampleDownloadUrl(generationId: string) {
  return (fmt: DocumentFormat) => `/examples/${generationId}/download/${fmt}`;
}

/** The examples' brand as the profile the card and document renderers take. Logos,
 *  uploaded fonts, and brand images are sign-in only, so they stay empty here. */
export function exampleBrandProfile(brand: ExampleBrand): BrandProfile {
  return {
    ...brand,
    logo: null,
    exemplars: [],
    brand_images: [],
    uploaded_fonts: [],
    card_presets: [],
  };
}
