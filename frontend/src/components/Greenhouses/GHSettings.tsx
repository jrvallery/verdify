import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Button, Flex, Heading, Input, Text, VStack } from "@chakra-ui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "@tanstack/react-router";
import { GreenhousesService, type GreenhousePublic } from "@/client";
import type { ApiError } from "@/client/core/ApiError";
import useCustomToast from "@/hooks/useCustomToast";
import { handleError } from "@/utils";

const loadLeaflet = (() => {
  let loaded: Promise<void> | null = null;
  return () => {
    if (loaded) return loaded;
    loaded = new Promise<void>((resolve, reject) => {
      // CSS
      const existingCss = document.querySelector('link[data-leaflet]');
      if (!existingCss) {
        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = "https://unpkg.com/leaflet/dist/leaflet.css";
        link.setAttribute("data-leaflet", "1");
        document.head.appendChild(link);
      }
      // JS
      if ((window as any).L) {
        resolve();
        return;
      }
      const script = document.createElement("script");
      script.src = "https://unpkg.com/leaflet/dist/leaflet.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load Leaflet"));
      document.body.appendChild(script);
    });
    return loaded;
  };
})();

const GHSettings = () => {
  const { greenhouseId } = useParams({ from: "/greenhouses/$greenhouseId/settings" });
  const router = useRouter();
  const queryClient = useQueryClient();
  const { showSuccessToast } = useCustomToast();

  const { data: greenhouse, isLoading } = useQuery({
    queryKey: ["greenhouse", greenhouseId],
    queryFn: () => GreenhousesService.readGreenhouse({ greenhouseId }),
    enabled: !!greenhouseId,
  });

  const [title, setTitle] = useState<string>("");
  const [latitude, setLatitude] = useState<number | undefined>(undefined);
  const [longitude, setLongitude] = useState<number | undefined>(undefined);

  useEffect(() => {
    if (greenhouse) {
      setTitle(greenhouse.title ?? "");
      setLatitude(greenhouse.latitude ?? undefined);
      setLongitude(greenhouse.longitude ?? undefined);
    }
  }, [greenhouse]);

  // Map setup
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapInstance = useRef<any>(null);
  const markerRef = useRef<any>(null);

  const initialView = useMemo<[number, number, number]>(() => {
    if (latitude !== undefined && longitude !== undefined) {
      return [latitude, longitude, 12];
    }
    return [39.5, -98.35, 4]; // USA center
  }, [latitude, longitude]);

  useEffect(() => {
    let disposed = false;
    if (!mapRef.current) return;

    loadLeaflet()
      .then(() => {
        if (disposed || !mapRef.current) return;
        const L = (window as any).L;

        // Create or reuse map
        if (!mapInstance.current) {
          mapInstance.current = L.map(mapRef.current).setView(
            [initialView[0], initialView[1]],
            initialView[2]
          );

          // Define tile layers
          const streetLayer = L.tileLayer(
            "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            { attribution: "© OpenStreetMap contributors" }
          );

          const satelliteLayer = L.tileLayer(
            "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            { attribution: "Tiles © Esri" }
          );

          // Add default layer and layer control
          streetLayer.addTo(mapInstance.current);
          L.control
            .layers(
              { "Street View": streetLayer, "Satellite View": satelliteLayer },
              {}
            )
            .addTo(mapInstance.current);

          // Initial marker if we have coords
          if (latitude !== undefined && longitude !== undefined) {
            markerRef.current = L.marker([latitude, longitude]).addTo(mapInstance.current);
          }

          // Click handler to drop/move pin
          mapInstance.current.on("click", (e: any) => {
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;

            if (markerRef.current) {
              mapInstance.current.removeLayer(markerRef.current);
            }
            markerRef.current = L.marker([lat, lng]).addTo(mapInstance.current);
            setLatitude(lat);
            setLongitude(lng);
          });
        } else {
          // If already exists, just set view/marker
          mapInstance.current.setView([initialView[0], initialView[1]], initialView[2]);
          if (latitude !== undefined && longitude !== undefined) {
            if (markerRef.current) {
              mapInstance.current.removeLayer(markerRef.current);
            }
            markerRef.current = L.marker([latitude, longitude]).addTo(mapInstance.current);
          }
        }
      })
      .catch(() => {
        // No-op: map optional
      });

    return () => {
      disposed = true;
    };
  }, [initialView, latitude, longitude]);

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<GreenhousePublic>) =>
      GreenhousesService.updateGreenhouse({
        greenhouseId,
        requestBody: {
          title: payload.title,
          latitude: payload.latitude,
          longitude: payload.longitude,
        } as any,
      }),
    onSuccess: () => {
      showSuccessToast("Greenhouse updated.");
      queryClient.invalidateQueries({ queryKey: ["greenhouse", greenhouseId] });
    },
    onError: (err: ApiError) => handleError(err),
  });

  const deleteMutation = useMutation({
    mutationFn: () => GreenhousesService.deleteGreenhouse({ greenhouseId }),
    onSuccess: () => {
      showSuccessToast("Greenhouse deleted.");
      queryClient.invalidateQueries({ queryKey: ["greenhouses"] });
      router.navigate({ to: "/" });
    },
    onError: (err: ApiError) => handleError(err),
  });

  const onSave = () => {
    updateMutation.mutate({
      title: title?.trim() || greenhouse?.title,
      latitude,
      longitude,
    } as Partial<GreenhousePublic>);
  };

  const onDelete = () => {
    deleteMutation.mutate();
  };

  return (
    <Box p={6}>
      <Heading size="lg" mb={6}>
        Greenhouse Settings
      </Heading>

      <VStack align="stretch" gap={4} maxW="640px">
        <Box>
          <Text mb={1} fontWeight="medium">
            Name
          </Text>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Greenhouse name"
            disabled={isLoading || updateMutation.isPending}
          />
        </Box>

        <Box>
          <Text mb={2} fontWeight="medium">
            Location
          </Text>
          <Box
            ref={mapRef}
            id="map"
            style={{ height: 360, borderRadius: 8, overflow: "hidden", border: "1px solid var(--chakra-colors-gray-200)" }}
          />
          <Flex gap={3} mt={3} wrap="wrap">
            <Input
              placeholder="Latitude"
              value={latitude ?? ""}
              onChange={(e) => setLatitude(e.target.value === "" ? undefined : Number(e.target.value))}
              type="number"
              step="any"
              width="xs"
            />
            <Input
              placeholder="Longitude"
              value={longitude ?? ""}
              onChange={(e) => setLongitude(e.target.value === "" ? undefined : Number(e.target.value))}
              type="number"
              step="any"
              width="xs"
            />
          </Flex>
          <Text mt={2} fontSize="xs" color="gray.500">
            Click on the map to drop a pin and set coordinates.
          </Text>
        </Box>

        <Flex gap={3}>
          <Button
            variant="solid"
            colorPalette="blue"
            onClick={onSave}
            loading={updateMutation.isPending}
          >
            Save Changes
          </Button>
          <Button
            variant="outline"
            onClick={() => {
              // Reset fields to current server values
              setTitle(greenhouse?.title ?? "");
              setLatitude(greenhouse?.latitude ?? undefined);
              setLongitude(greenhouse?.longitude ?? undefined);
            }}
            disabled={isLoading || updateMutation.isPending}
          >
            Reset
          </Button>
        </Flex>

        <Box mt={8} borderTop="1px" borderColor="gray.200" pt={4}>
          <Heading size="sm" color="red.600" mb={2}>
            Danger Zone
          </Heading>
          <Text fontSize="sm" color="gray.600" mb={3}>
            Deleting a greenhouse cannot be undone.
          </Text>
          <form onSubmit={(e) => { e.preventDefault(); onDelete(); }}>
            <Button
              variant="solid"
              colorPalette="red"
              type="submit"
              loading={deleteMutation.isPending}
            >
              Delete Greenhouse
            </Button>
          </form>
        </Box>
      </VStack>
    </Box>
  );
};

export default GHSettings;
