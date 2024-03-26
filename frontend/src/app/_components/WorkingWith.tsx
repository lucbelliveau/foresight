"use client";

import Typography from "@mui/material/Typography";
import { useStore } from "~/app/_store";

export default function WorkingWith() {
  const { articleCount } = useStore();
  if (articleCount === 0) return;

  return (
    <Typography variant="body1" fontSize={16}>
      You are working with{" "}
      <Typography variant="body1" fontSize={22} component="span">
        {articleCount.toLocaleString()}
      </Typography>{" "}
      articles.
    </Typography>
  );
}
