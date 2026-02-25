import { GitHubLogoIcon } from "@radix-ui/react-icons";

import { AuroraText } from "@/components/ui/aurora-text";
import { Button } from "@/components/ui/button";

import { Section } from "../section";

export function CommunitySection() {
  return (
    <Section
      title={
        <AuroraText colors={["#60A5FA", "#A5FA60", "#A560FA"]}>
          Join the Community
        </AuroraText>
      }
      subtitle="Contribute brilliant ideas to shape the future of Thinktank.ai. Collaborate, innovate, and make impacts."
    >
      <div className="flex justify-center">
        <Button className="text-xl" size="lg" asChild>
          <a href="https://github.com/thinktank-ai/thinktank-ai" target="_blank" rel="noopener noreferrer">
            <GitHubLogoIcon />
            Contribute Now
          </a>
        </Button>
      </div>
    </Section>
  );
}
